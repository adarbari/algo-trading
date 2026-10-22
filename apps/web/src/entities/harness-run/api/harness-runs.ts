/**
 * The read hooks for the edge evaluation runs over GraphQL (`Query.harnessRuns` and
 * `Query.harnessRun`, Admin only; ADR 0053, ADR 0037): the list of runs of any status with what
 * each measured and left out, and one run's rows, read by run id.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

export const RUN_LIMIT = 100;

const HarnessRunsQuery = graphql(`
  query HarnessRuns($limit: Int!) {
    harnessRuns(limit: $limit) {
      runId
      edgeId
      user
      status
      startedAt
      finishedAt
      rangeFrom
      rangeTo
      splitFrom
      exploratory
      variants
      horizons
      sessions
      unclosed
      excludedCoverage
      scoreCoverage
      noEntryBar
      trials
      knowledgeTs
      asOf
    }
  }
`);

const HarnessRunQuery = graphql(`
  query HarnessRun($runId: String!) {
    harnessRun(runId: $runId) {
      runId
      lostInputs {
        variant
        horizon
        table
        sessions
      }
      rows {
        edgeVariant
        variant
        role
        horizonSessions
        sliceKind
        sliceValue
        sessions
        picks
        hits
        trials
        hitRate
        baseRate
        lift
        decileSpread
        exploratory
      }
    }
  }
`);

function harnessRunsQuery(limit = RUN_LIMIT) {
  return queryOptions({
    queryKey: queryKeys.gql('HarnessRuns', { limit }),
    queryFn: ({ queryKey }) => gql(HarnessRunsQuery, { limit }, queryKey),
  });
}

/** Start the read before the page mounts (a route loader); the hook then joins it. */
export function prefetchHarnessRuns(client: QueryClient, limit = RUN_LIMIT): void {
  void client.query(harnessRunsQuery(limit)).catch(() => undefined);
}

/** The evaluation runs, newest first. */
export function useHarnessRuns(limit = RUN_LIMIT) {
  return useQuery({
    ...harnessRunsQuery(limit),
    select: (data) => data.harnessRuns,
  });
}

/** One run's rows (null: no such run); idle until a run is chosen. */
export function useHarnessRunRows(runId: string | null) {
  return useQuery({
    queryKey: queryKeys.gql('HarnessRun', { runId }),
    queryFn: ({ queryKey }) => gql(HarnessRunQuery, { runId: runId ?? '' }, queryKey),
    select: (data) => data.harnessRun,
    enabled: runId !== null,
  });
}
