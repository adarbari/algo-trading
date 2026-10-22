/**
 * Every rule screener's run summary for the latest session in one light read (GraphQL
 * `screeners`: its criteria, its run's pick count and decision counts, or why it has no run), for
 * the Screeners list's rows. The rows themselves (`useScreenerResults`) load only when a screener
 * is opened.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

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
        op
        value
      }
      notRun {
        kindText
      }
      pickHistory {
        session
        picked
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

const runsQuery = () =>
  queryOptions({
    queryKey: queryKeys.gql('ScreenerRuns', {}),
    queryFn: ({ queryKey }) => gql(ScreenerRuns, {}, queryKey),
  });

/** Start reading the run summaries before the page mounts (a route loader). */
export function prefetchScreenerRuns(client: QueryClient): void {
  void client.query(runsQuery()).catch(() => undefined);
}

/** The summaries by screener id, and the session they are for (null: nothing stored). */
export function useScreenerRuns() {
  return useQuery({
    ...runsQuery(),
    select: (data) => ({
      session: data.session?.date ?? null,
      byId: new Map(data.screeners.map((s) => [s.id, s])),
    }),
  });
}
