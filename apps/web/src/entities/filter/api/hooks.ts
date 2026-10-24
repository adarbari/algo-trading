/**
 * The read hook for a surface's filter definitions (`Query.filterSet`, ADR 0082): the filters the
 * viewer may use, in the order a group lists them. They change only with a release or a licence,
 * so they are cached for a while; the counts come with each list's own read (`facets`).
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

export const FILTER_SET_OPERATION = 'FilterSet';

const STALE_MS = 10 * 60_000;

const FilterSetQuery = graphql(`
  query FilterSet($surface: String!) {
    filterSet(surface: $surface) {
      surface
      label
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
      }
    }
  }
`);

function filterSetOptions(surface: string) {
  return queryOptions({
    queryKey: queryKeys.gql(FILTER_SET_OPERATION, { surface }),
    queryFn: ({ queryKey }) => gql(FilterSetQuery, { surface }, queryKey),
    staleTime: STALE_MS,
  });
}

/** The definitions of one surface (`filterSet` null: no such surface). */
export function useFilterSet(surface: string) {
  return useQuery(filterSetOptions(surface));
}

/** Start the definitions' read before the page mounts. */
export function prefetchFilterSet(client: QueryClient, surface: string): void {
  void client.query(filterSetOptions(surface)).catch(() => undefined);
}
