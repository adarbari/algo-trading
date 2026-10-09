/**
 * The instrument ids a screener's latest run picked, as light as the read allows (GraphQL
 * `ScreenerRun.pickIds`, ADR 0037): the calendar needs only who was picked, not a review
 * table's criteria, columns and reasons per row, so the server reads the run's rows alone (no criterion values) and the query
 * selects the ids and the total.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

export const SCREENER_PICKS_OPERATION = 'ScreenerPicks';

/** The most picks one read returns (the API's page cap). */
export const PICKS_LIMIT = 1000;

const ScreenerPicks = graphql(`
  query ScreenerPicks($id: String!, $size: Int) {
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
        pickIds(size: $size) {
          total
          instrumentIds
        }
      }
    }
  }
`);

export type ScreenerPicksResponse = gqlTypes.ScreenerPicksQuery;

/** Screener `id`'s picks in its latest run (null `screener`: not one the user sees). */
export function useScreenerPicks(id: string, enabled = true) {
  const variables = { id, size: PICKS_LIMIT };
  return useQuery({
    queryKey: queryKeys.gql(SCREENER_PICKS_OPERATION, variables),
    queryFn: () => gql(ScreenerPicks, variables),
    enabled,
  });
}
