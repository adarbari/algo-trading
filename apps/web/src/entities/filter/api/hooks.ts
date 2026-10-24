/**
 * The read hooks for a surface's filter definitions (`Query.filterSet`, ADR 0082): the filters the
 * viewer may use, in the order a group lists them, plus the filters made on the fly from catalogue
 * features the viewer picked (`withFeatures`: the id `feature:<field>`), and the features they may
 * pick (`filterFeatures`: licence-gated and with the phrasebook's words, "More filters"). They
 * change only with a release or a licence, so they are cached for a while; the counts come with
 * each list's own read (`facets`).
 */
import { keepPreviousData, queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

export const FILTER_SET_OPERATION = 'FilterSet';

const STALE_MS = 10 * 60_000;

const FilterSetQuery = graphql(`
  query FilterSet($surface: String!, $withFeatures: [String!]) {
    filterSet(surface: $surface, withFeatures: $withFeatures) {
      surface
      label
      searchable
      filters {
        id
        label
        group
        kind
        guide
        options {
          value
          label
        }
        bins
        windowUnit
        unit
      }
    }
  }
`);

const FilterFeaturesQuery = graphql(`
  query FilterFeatures($surface: String!) {
    filterFeatures(surface: $surface) {
      name
      label
      kind
      guide
      synonyms
    }
  }
`);

function filterSetOptions(surface: string, features: readonly string[]) {
  const variables = { surface, ...(features.length > 0 && { withFeatures: [...features] }) };
  return queryOptions({
    queryKey: queryKeys.gql(FILTER_SET_OPERATION, variables),
    queryFn: ({ queryKey }) =>
      gql(FilterSetQuery, { ...variables, withFeatures: variables.withFeatures ?? null }, queryKey),
    staleTime: STALE_MS,
  });
}

/**
 * The definitions of one surface (`filterSet` null: no such surface), with the filters made of
 * `features` (catalogue fields). The last answer stays while a new feature's definition loads.
 */
export function useFilterSet(surface: string, features: readonly string[] = NO_FEATURES) {
  return useQuery({ ...filterSetOptions(surface, features), placeholderData: keepPreviousData });
}

const NO_FEATURES: readonly string[] = [];

/** The catalogue fields the viewer may pick as filters of the surface (read once the search opens). */
export function useFilterFeatures(surface: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.gql('FilterFeatures', { surface }),
    queryFn: ({ queryKey }) => gql(FilterFeaturesQuery, { surface }, queryKey),
    staleTime: STALE_MS,
    enabled,
  });
}

/** Start the definitions' read before the page mounts. */
export function prefetchFilterSet(client: QueryClient, surface: string): void {
  void client.query(filterSetOptions(surface, NO_FEATURES)).catch(() => undefined);
}
