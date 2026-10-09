/**
 * Read hooks for rule screens: the screener configs (GraphQL `configs`), the user's own screens
 * and one screen's draft, versions and preset pin (GraphQL `myScreens`, `screenDetail`,
 * `screenVersions`; ADR 0037), the live preview of a draft (a preview POST) and a run on
 * request. A screener's results are `useScreenerResults` (`./results`). The writes stay REST
 * (features/screener-*); after one, `refreshScreens` reads them all again.
 */
import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api, gql, graphql, queryKeys, unwrap } from '@/shared/api';

import type { ScreenDocument, ScreenerDetail } from '../model/spec';
import { isActive } from '../model/run';

import { SCREENER_RESULTS_OPERATION } from './results';

const ScreenerConfigs = graphql(`
  query ScreenerConfigs {
    configs(kind: "screener") {
      configId
      scope
      kind
      impl
      selection
      hash
      error
    }
  }
`);

const MyScreens = graphql(`
  query MyScreens {
    myScreens {
      screenerId
      status
      latest
      hasDraft
      presetId
    }
  }
`);

const ScreenDetail = graphql(`
  query ScreenDetail($id: String!) {
    screenDetail(screenerId: $id) {
      screenerId
      user
      draft
      draftError
      versions
      latest
      preset {
        presetId
        pinned
        current
        rebaseAvailable
      }
      hash
      layers
      resolved
      error
      working
    }
  }
`);

const ScreenVersions = graphql(`
  query ScreenVersions($id: String!) {
    screenVersions(screenerId: $id) {
      version
      document
    }
  }
`);

/** The screen operations, so a write can read them all again. */
const SCREEN_OPERATIONS = [
  'ScreenerConfigs',
  'MyScreens',
  'ScreenDetail',
  'ScreenVersions',
  SCREENER_RESULTS_OPERATION,
];

/** Read every screen list and detail again (after a draft, finalise, copy or delete). */
export async function refreshScreens(client: QueryClient): Promise<void> {
  await Promise.all(
    SCREEN_OPERATIONS.map((name) => client.invalidateQueries({ queryKey: ['gql', name] })),
  );
}

/** Drop one screen's cached detail (it no longer exists). */
export function forgetScreen(client: QueryClient, id: string): void {
  client.removeQueries({ queryKey: queryKeys.gql('ScreenDetail', { id }) });
}

/** Every screener config the user sees: site presets and their own (Python and rule screens). */
export function useScreeners() {
  return useQuery({ ...screenerConfigsQuery(), select: (data) => data.configs });
}

const screenerConfigsQuery = () =>
  queryOptions({
    queryKey: queryKeys.gql('ScreenerConfigs', {}),
    queryFn: () => gql(ScreenerConfigs, {}),
  });

/** Start reading the screener list before the page opens (a link was hovered): a no-op while fresh. */
export function prefetchScreeners(client: QueryClient): void {
  void client.query(screenerConfigsQuery()).catch(() => undefined);
}

/** The user's own screens: finalized ones and draft-only ones (status DRAFT). */
export function useMyScreeners() {
  return useQuery({
    queryKey: queryKeys.gql('MyScreens', {}),
    queryFn: () => gql(MyScreens, {}),
    select: (data) => data.myScreens,
  });
}

/**
 * One screen: its draft, versions, preset pin and resolved working copy; `null` when the user
 * has no such screen (and there is no preset of that id).
 */
export function useScreener(id: string | null) {
  const variables = { id: id ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('ScreenDetail', variables),
    queryFn: () => gql(ScreenDetail, variables),
    // The JSON documents are the screen's TOML tables (objects) as stored.
    select: (data) => data.screenDetail as ScreenerDetail | null,
    enabled: Boolean(id),
    retry: false,
  });
}

/** The finalised versions of a screen (oldest first), each with its document. */
export function useScreenerVersions(id: string | null, enabled = true) {
  const variables = { id: id ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('ScreenVersions', variables),
    queryFn: () => gql(ScreenVersions, variables),
    select: (data) =>
      data.screenVersions.map((v) => ({
        version: v.version,
        document: v.document as Record<string, unknown>,
      })),
    enabled: Boolean(id) && enabled,
  });
}

/** The fewest top rows the preview returns (it returns every row not rejected besides). */
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

/** How often a requested run is polled while it is queued or running. */
export const RUN_POLL_MS = 1500;

/**
 * Run a screener on request (POST /screens/{id}/run) and follow it: the API answers `ready`
 * when this version has already run for the latest session, else starts the nightly's `screen`
 * job; the job is polled until it finishes, and then the screener's results are read again.
 */
export function useRunScreener(id: string) {
  const client = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const refresh = () =>
    client.invalidateQueries({ queryKey: queryKeys.gqlAll(SCREENER_RESULTS_OPERATION) });
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
    queryFn: () => unwrap(api.GET('/jobs/{job_id}', { params: { path: { job_id: jobId ?? '' } } })),
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
