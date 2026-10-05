/**
 * Read hooks for rule screens: the screeners list (GET /configs), one screen's draft, versions
 * and preset pin (GET /screeners/{id}), and the live preview of a draft.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api, queryKeys, unwrap } from '@/shared/api';

import type { ScreenDocument } from '../model/spec';
import { isActive } from '../model/run';
import { tableParams, type ScreenerView, type ScreenTableQuery } from '../model/table';

/** Every screener the user sees: site presets and their own (Python and rule screens). */
export function useScreeners() {
  return useQuery({
    queryKey: queryKeys.screeners.list(),
    queryFn: () => unwrap(api.GET('/configs')),
    select: (configs) => configs.filter((c) => c.kind === 'screener'),
  });
}

/** The user's own screens: finalized ones and draft-only ones (status DRAFT). */
export function useMyScreeners() {
  return useQuery({
    queryKey: queryKeys.screeners.mine(),
    queryFn: () => unwrap(api.GET('/screeners')),
  });
}

/** One screen: its draft, versions, preset pin and resolved working copy. */
export function useScreener(id: string | null) {
  return useQuery({
    queryKey: queryKeys.screeners.detail(id ?? ''),
    queryFn: () =>
      unwrap(api.GET('/screeners/{screener_id}', { params: { path: { screener_id: id ?? '' } } })),
    enabled: Boolean(id),
    retry: false,
  });
}

/** The finalised versions of a screen (oldest first), each with its document. */
export function useScreenerVersions(id: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.screeners.versions(id ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/screeners/{screener_id}/versions', {
          params: { path: { screener_id: id ?? '' } },
        }),
      ),
    enabled: Boolean(id) && enabled,
  });
}

/** How many top rows the preview returns. */
export const PREVIEW_ROWS = 50;

/**
 * The preview of an unsaved draft on the latest closed session. The caller debounces the
 * document (300 ms); the previous result stays on screen while a new one loads.
 */
export function useScreenPreview(document: ScreenDocument | null) {
  return useQuery({
    queryKey: queryKeys.screeners.preview(document),
    queryFn: () =>
      unwrap(
        api.POST('/screeners/preview', { body: { spec: document ?? {}, limit: PREVIEW_ROWS } }),
      ),
    enabled: document !== null,
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: 30_000,
  });
}

/**
 * A rule screen's latest run as a review table: filtered, sorted and cut to the first
 * `TABLE_ROWS` rows by the API. The previous table stays on screen while a new one loads.
 * A screen with no stored run answers 404 (no retry).
 */
export function useScreenTable(id: string, query: ScreenTableQuery, enabled = true) {
  return useQuery({
    queryKey: queryKeys.screeners.table(id, { ...query }),
    queryFn: () =>
      unwrap(
        api.GET('/screens/{config_id}/table', {
          params: { path: { config_id: id }, query: tableParams(query) },
        }),
      ),
    placeholderData: keepPreviousData,
    enabled,
    retry: false,
  });
}

/** The user's saved view of a screen's results (columns, sort, decisions). */
export function useScreenerView(id: string) {
  return useQuery({
    queryKey: queryKeys.screeners.view(id),
    queryFn: () =>
      unwrap(
        api.GET('/preferences/screeners/{screener_id}/view', {
          params: { path: { screener_id: id } },
        }),
      ),
  });
}

/** Saves the view (it belongs to the user, not to the screen: no version, no hash). */
export function useSaveScreenerView(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (view: Pick<ScreenerView, 'columns' | 'sort' | 'decisions'>) =>
      unwrap(
        api.PUT('/preferences/screeners/{screener_id}/view', {
          params: { path: { screener_id: id } },
          body: view,
        }),
      ),
    onSuccess: (saved) => {
      client.setQueryData(queryKeys.screeners.view(id), saved);
    },
  });
}

/** How often a requested run is polled while it is queued or running. */
export const RUN_POLL_MS = 1500;

/**
 * Run a screener on request (POST /screens/{id}/run) and follow it: the API answers `ready`
 * when this version has already run for the latest session, else starts the nightly's `screen`
 * job; the job is polled until it finishes, and then the screener's tables are fetched again.
 */
export function useRunScreener(id: string) {
  const client = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const refresh = () => client.invalidateQueries({ queryKey: queryKeys.screeners.tables(id) });
  const start = useMutation({
    mutationFn: () =>
      unwrap(api.POST('/screens/{config_id}/run', { params: { path: { config_id: id } } })),
    onSuccess: (run) => {
      setJobId(run.job_id ?? null);
      if (!isActive(run)) void refresh();
    },
  });
  const status = useQuery({
    queryKey: queryKeys.screeners.run(id, jobId ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/screens/{config_id}/run/{job_id}', {
          params: { path: { config_id: id, job_id: jobId ?? '' } },
        }),
      ),
    enabled: jobId !== null && isActive(start.data),
    refetchInterval: (query) => (isActive(query.state.data) ? RUN_POLL_MS : false),
    retry: false,
  });
  const run = status.data ?? start.data;
  const finished = run !== undefined && !isActive(run);
  useEffect(() => {
    if (finished && jobId !== null) void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh only when the run finishes
  }, [finished, jobId]);
  return {
    start: () => {
      start.mutate();
    },
    run,
    running: start.isPending || isActive(run),
    error: start.error ?? status.error,
  };
}
