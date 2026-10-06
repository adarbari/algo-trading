/**
 * A screener's latest run as a review table over GraphQL (ADR 0037, read-model PR 8): the
 * screener (criteria, display columns), its run for the latest session (decision counts, the
 * changes since the previous run) and one page of its rows, filtered, sorted and paged on the
 * server, with the catalogue columns the reader added (a feature table's cells).
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

import { resultsVariables, type ScreenResultsQuery } from '../model/results';

export const SCREENER_RESULTS_OPERATION = 'ScreenerResults';

const ScreenerResults = graphql(`
  query ScreenerResults(
    $id: String!
    $decisions: [String!]
    $change: String
    $q: String
    $sort: String
    $columns: [FeatureName!]
    $page: Int
    $size: Int
  ) {
    session {
      date
      missing
    }
    screener(id: $id) {
      id
      name
      criteria {
        id
        field
        mode
      }
      displayColumns {
        name
        field
      }
      notRun {
        code
        detail
      }
      latestRun {
        runId
        session
        previousSession
        regime
        paused
        decisions {
          decision
          count
        }
        changes {
          change
          count
        }
        results(
          decisions: $decisions
          change: $change
          q: $q
          sort: $sort
          columns: $columns
          page: $page
          size: $size
        ) {
          sort
          total
          page
          size
          missing
          columns {
            name
            description
            format
            unit
            dtype
            nullMeaning
            licence
            scope
          }
          rows
          unknown
          reasons
          results {
            instrumentId
            rank
            decision
            score
            reasons
            flags
            change
            previousDecision
            instrument {
              instrumentId
              symbol
              name
            }
            criteria {
              id
              field
              mode
              outcome
              value
              distance
            }
            columns {
              name
              value
            }
          }
        }
      }
    }
  }
`);

export type ScreenerResultsResponse = gqlTypes.ScreenerResultsQuery;

/**
 * One page of screener `id`'s latest run as `query` asks; the previous page stays on screen
 * while the next loads. `data.screener` is null for a screener the user does not see.
 */
export function useScreenerResults(id: string, query: ScreenResultsQuery, enabled = true) {
  const variables = resultsVariables(id, query);
  return useQuery({
    queryKey: queryKeys.gql(SCREENER_RESULTS_OPERATION, variables),
    queryFn: () => gql(ScreenerResults, variables),
    placeholderData: keepPreviousData,
    enabled,
  });
}
