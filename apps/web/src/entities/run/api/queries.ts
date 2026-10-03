/** Read hooks for runs: recent nightly runs, one run record, its items, the quality checks. */
import { queryOptions, useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

export const NIGHTLY_LIMIT = 10;

export function useNightlyRuns(limit = NIGHTLY_LIMIT) {
  return useQuery({
    queryKey: queryKeys.admin.nightlyRuns(limit),
    queryFn: () => unwrap(api.GET('/admin/runs/nightly', { params: { query: { limit } } })),
  });
}

export function useRun(runId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.admin.run(runId ?? ''),
    queryFn: () =>
      unwrap(api.GET('/admin/runs/{run_id}', { params: { path: { run_id: runId ?? '' } } })),
    enabled: Boolean(runId),
  });
}

/** Every item of one run (also fetched on demand, e.g. for a CSV download). */
export function runItemsQuery(runId: string) {
  return queryOptions({
    queryKey: queryKeys.admin.runItems(runId),
    queryFn: () =>
      unwrap(api.GET('/admin/runs/{run_id}/items', { params: { path: { run_id: runId } } })),
  });
}

export function useRunItems(runId: string | null | undefined, enabled = true) {
  return useQuery({ ...runItemsQuery(runId ?? ''), enabled: Boolean(runId) && enabled });
}

export function useQualityChecks() {
  return useQuery({
    queryKey: queryKeys.admin.quality(),
    queryFn: () => unwrap(api.GET('/admin/quality')),
  });
}
