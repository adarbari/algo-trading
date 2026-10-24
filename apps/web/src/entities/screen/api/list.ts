/**
 * The Screeners list's narrowing (GraphQL `screenerList`, ADR 0082): the ids of the screeners that
 * pass the filters in force and match the search (name, description, id), and the counts the
 * filter bar shows. The rows themselves come from the list's other reads; this says which of
 * them stay. The last answer stays while a new one loads.
 */
import { keepPreviousData, queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import { toFilterInputs, type AppliedFilter, type FilterInput } from '@/entities/filter';
import { gql, graphql, queryKeys } from '@/shared/api';

const ScreenerListPage = graphql(`
  query ScreenerListPage($filters: [FilterInput!], $q: String) {
    screenerList(filters: $filters, q: $q) {
      total
      facets {
        total
        matched
        items {
          id
          active
          removes
          unknown
          options {
            value
            count
          }
          bins {
            lo
            hi
            count
          }
        }
      }
      items {
        id
      }
    }
  }
`);

const NO_FILTERS: readonly AppliedFilter[] = [];

const listQuery = (filters: readonly FilterInput[] | null, q: string) => {
  const variables = { ...(filters && { filters: [...filters] }), ...(q && { q }) };
  return queryOptions({
    queryKey: queryKeys.gql('ScreenerListPage', variables),
    queryFn: ({ queryKey }) =>
      gql(
        ScreenerListPage,
        { filters: variables.filters ?? null, q: variables.q ?? null },
        queryKey,
      ),
  });
};

/** Start the narrowing's read before the page mounts (a route loader). */
export function prefetchScreenerList(
  client: QueryClient,
  applied: readonly AppliedFilter[] = NO_FILTERS,
  q = '',
): void {
  void client.query(listQuery(toFilterInputs(applied), q)).catch(() => undefined);
}

/** The screeners passing `applied` and `q`: their ids and the filter bar's counts (null: nothing stored). */
export function useScreenerList(applied: readonly AppliedFilter[] = NO_FILTERS, q = '') {
  const filters = useMemo(() => toFilterInputs(applied), [applied]);
  return useQuery({
    ...listQuery(filters, q),
    placeholderData: keepPreviousData,
    select: (data) =>
      data.screenerList && {
        ids: new Set(data.screenerList.items.map((s) => s.id)),
        facets: data.screenerList.facets,
      },
  });
}
