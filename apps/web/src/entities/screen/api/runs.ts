/**
 * Every rule screener's run summary for the latest session in one light read (GraphQL
 * `screeners`: its criteria, its run's pick count and decision counts, or why it has no run), for
 * the Screeners list's rows. The rows themselves (`useScreenerResults`) load only when a screener
 * is opened.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const ScreenerRuns = graphql(`
  query ScreenerRuns {
    session {
      date
    }
    screeners {
      id
      name
      criteria {
        id
        field
        mode
      }
      notRun {
        kindText
      }
      latestRun {
        runId
        session
        picked
        paused
        decisions {
          decision
          count
        }
        changes {
          change
          count
        }
      }
    }
  }
`);

export type ScreenerRunSummary = gqlTypes.ScreenerRunsQuery['screeners'][number];

/** The summaries by screener id, and the session they are for (null: nothing stored). */
export function useScreenerRuns() {
  return useQuery({
    queryKey: queryKeys.gql('ScreenerRuns', {}),
    queryFn: () => gql(ScreenerRuns, {}),
    select: (data) => ({
      session: data.session?.date ?? null,
      byId: new Map(data.screeners.map((s) => [s.id, s])),
    }),
  });
}
