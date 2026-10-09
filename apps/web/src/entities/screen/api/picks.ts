/**
 * The instrument ids a screener's latest run picked, as light as the read allows (GraphQL
 * `ScreenerRun.results`, ADR 0037): the calendar needs only who was picked, not a review
 * table's criteria, columns and reasons per row, so the query selects the ids and the total.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

import { DEFAULT_DECISIONS } from '../model/results';

export const SCREENER_PICKS_OPERATION = 'ScreenerPicks';

/** The most picks one read returns (the API's page cap). */
export const PICKS_LIMIT = 1000;

const ScreenerPicks = graphql(`
  query ScreenerPicks($id: String!, $decisions: [String!], $size: Int) {
    screener(id: $id) {
      id
      notRun {
        code
        kind
        guideTerm
        kindText
        cause {
          links {
            level
            subject
            status
            message
            runId
          }
        }
      }
      latestRun {
        runId
        results(decisions: $decisions, size: $size) {
          total
          results {
            instrumentId
          }
        }
      }
    }
  }
`);

export type ScreenerPicksResponse = gqlTypes.ScreenerPicksQuery;

/** Screener `id`'s picks in its latest run (null `screener`: not one the user sees). */
export function useScreenerPicks(id: string, enabled = true) {
  const variables = { id, decisions: [...DEFAULT_DECISIONS], size: PICKS_LIMIT };
  return useQuery({
    queryKey: queryKeys.gql(SCREENER_PICKS_OPERATION, variables),
    queryFn: () => gql(ScreenerPicks, variables),
    enabled,
  });
}
