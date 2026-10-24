/**
 * The read hooks for the screener runs over GraphQL (`Query.screenerRuns` and
 * `Query.screenerRun`, Admin only; ADR 0033, ADR 0037): every run of any status, newest first,
 * narrowed on the server by user, screener and status, and one run's full record by run id.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { ScreenerRunFilters } from '../model/filters';

export const RUN_LIMIT = 100;

const AdminScreenerRunsQuery = graphql(`
  query AdminScreenerRuns($limit: Int!, $user: String, $screener: String, $status: String) {
    screenerRuns(limit: $limit, user: $user, screener: $screener, status: $status) {
      runId
      configId
      owner
      session
      status
      startedAt
      finishedAt
      knowledgeTs
      picked
      paused
      regime
      coverage
    }
  }
`);

const AdminScreenerRunQuery = graphql(`
  query AdminScreenerRun($runId: String!) {
    screenerRun(runId: $runId) {
      runId
      configId
      owner
      session
      status
      startedAt
      finishedAt
      knowledgeTs
      configVersion
      configHash
      decisions {
        decision
        count
      }
      picked
      paused
      regime
      coverage
      missingTables
      missingOptionalTables
      unavailable {
        kind
        features
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
      changes {
        picked
        paused
        previousRunId
        previousSession
        previousVersion
        newPicks
        dropped
      }
    }
  }
`);

function variables(filters: ScreenerRunFilters, limit: number) {
  return {
    limit,
    user: filters.user ?? null,
    screener: filters.screener ?? null,
    status: filters.status ?? null,
  };
}

function screenerRunsQuery(filters: ScreenerRunFilters = {}, limit = RUN_LIMIT) {
  const vars = variables(filters, limit);
  return queryOptions({
    queryKey: queryKeys.gql('AdminScreenerRuns', vars),
    queryFn: ({ queryKey }) => gql(AdminScreenerRunsQuery, vars, queryKey),
  });
}

/** Start the read before the page mounts (a route loader); the hook then joins it. */
export function prefetchScreenerRuns(
  client: QueryClient,
  filters: ScreenerRunFilters = {},
  limit = RUN_LIMIT,
): void {
  void client.query(screenerRunsQuery(filters, limit)).catch(() => undefined);
}

/** The screener runs, newest first, narrowed by the filters the server applies. */
export function useScreenerRuns(filters: ScreenerRunFilters = {}, limit = RUN_LIMIT) {
  return useQuery({
    ...screenerRunsQuery(filters, limit),
    select: (data) => data.screenerRuns,
  });
}

/** One run's record (null: no such run); idle until a run is chosen. */
export function useScreenerRun(runId: string | null) {
  return useQuery({
    queryKey: queryKeys.gql('AdminScreenerRun', { runId }),
    queryFn: ({ queryKey }) => gql(AdminScreenerRunQuery, { runId: runId ?? '' }, queryKey),
    select: (data) => data.screenerRun,
    enabled: runId !== null,
  });
}
