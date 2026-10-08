/**
 * Read hooks for runs over GraphQL (ADR 0037): recent nightly runs, one run record, its items
 * (`Query.{nightlyRuns,run,runItems}`, run records: no session) and the session's data-quality
 * checks (`Query.quality`, for exactly the latest session: NOT_RUN when it has none).
 */
import { queryOptions, useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { toRunDetail } from '../model/run';

export const NIGHTLY_LIMIT = 10;

const NightlyRuns = graphql(`
  query NightlyRuns($limit: Int!) {
    nightlyRuns(limit: $limit) {
      runId
      session
      status
      startedAt
      finishedAt
      durationS
      problems
      steps {
        name
        status
        durationS
        reason
        error
      }
    }
  }
`);

const RunRecord = graphql(`
  query RunRecord($runId: String!) {
    run(runId: $runId) {
      runId
      job
      session
      status
      startedAt
      finishedAt
      durationS
      itemsTotal
      itemsByStatus
      stats
      failures {
        reason
        count
        examples
        statuses
      }
    }
  }
`);

const RunItems = graphql(`
  query RunItems($runId: String!) {
    runItems(runId: $runId) {
      key
      code
      status
    }
  }
`);

const QualityChecks = graphql(`
  query QualityChecks {
    quality {
      session
      runId
      status
      finishedAt
      checks {
        name
        status
        detail
      }
      unknown {
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
    }
  }
`);

/** The newest nightly runs; `enabled: false` skips the read (the viewer may not see runs). */
export function useNightlyRuns(limit = NIGHTLY_LIMIT, enabled = true) {
  return useQuery({
    enabled,
    queryKey: queryKeys.gql('NightlyRuns', { limit }),
    queryFn: () => gql(NightlyRuns, { limit }),
    select: (data) => data.nightlyRuns,
  });
}

/** One run record; null: no such run. */
export function useRun(runId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.gql('RunRecord', { runId: runId ?? '' }),
    queryFn: () => gql(RunRecord, { runId: runId ?? '' }),
    select: (data) => (data.run ? toRunDetail(data.run) : null),
    enabled: Boolean(runId),
  });
}

/** Every item of one run (also fetched on demand, e.g. for a CSV download); no such run fails. */
export function runItemsQuery(runId: string) {
  return queryOptions({
    queryKey: queryKeys.gql('RunItems', { runId }),
    queryFn: async () => {
      const { runItems } = await gql(RunItems, { runId });
      if (!runItems) throw new Error(`no run ${runId}`);
      return runItems;
    },
  });
}

export function useRunItems(runId: string | null | undefined, enabled = true) {
  return useQuery({ ...runItemsQuery(runId ?? ''), enabled: Boolean(runId) && enabled });
}

/** The latest session's data-quality checks; null: nothing stored. */
export function useQualityChecks() {
  return useQuery({
    queryKey: queryKeys.gql('QualityChecks', {}),
    queryFn: () => gql(QualityChecks, {}),
    select: (data) => data.quality,
  });
}
