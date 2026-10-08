/**
 * The read hooks for the edge evaluation runs over GraphQL (`Query.harnessRuns` and
 * `Query.harnessRun`, Admin only; ADR 0053, ADR 0037): the list of runs of any status with what
 * each measured and left out, and one run's rows, read by run id.
 */
import { useQuery } from '@tanstack/react-query';

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

/** The evaluation runs, newest first. */
export function useHarnessRuns(limit = RUN_LIMIT) {
  return useQuery({
    queryKey: queryKeys.gql('HarnessRuns', { limit }),
    queryFn: () => gql(HarnessRunsQuery, { limit }),
    select: (data) => data.harnessRuns,
  });
}

/** One run's rows (null: no such run); idle until a run is chosen. */
export function useHarnessRunRows(runId: string | null) {
  return useQuery({
    queryKey: queryKeys.gql('HarnessRun', { runId }),
    queryFn: () => gql(HarnessRunQuery, { runId: runId ?? '' }),
    select: (data) => data.harnessRun,
    enabled: runId !== null,
  });
}
