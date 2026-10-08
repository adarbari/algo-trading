/**
 * Read hook for the Guide search (`Query.guideSearch`, ADR 0037 / 0051): the results for a
 * query, grouped by kind and ranked by the server, which re-reads the Guide's sources on every
 * request. Nothing is ranked or filtered in the browser (ADR 0038), and nothing is read for an
 * empty query.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

/** Results per kind: the dialog shows a handful of each, the full pages hold the rest. */
export const SEARCH_LIMIT_PER_KIND = 6;

const GuideSearchQuery = graphql(`
  query GuideSearch($q: String!, $limit: Int!) {
    guideSearch(q: $q, limit: $limit) {
      query
      groups {
        kind
        hits {
          kind
          id
          title
          snippet
        }
      }
    }
  }
`);

/** The result groups for `q`, the previous ones kept on screen while the next are read. */
export function useGuideSearchResults(q: string) {
  const variables = { q, limit: SEARCH_LIMIT_PER_KIND };
  return useQuery({
    queryKey: queryKeys.gql('GuideSearch', variables),
    queryFn: () => gql(GuideSearchQuery, variables),
    select: (data) => data.guideSearch?.groups ?? [],
    enabled: q !== '',
    // The server computes from the sources per request: never serve an old answer as fresh.
    staleTime: 0,
    gcTime: 30_000,
    placeholderData: keepPreviousData,
  });
}
