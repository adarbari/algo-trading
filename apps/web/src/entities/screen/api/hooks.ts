/**
 * Read hooks for rule screens: the screeners list (GET /configs), one screen's draft, versions
 * and preset pin (GET /screeners/{id}), and the live preview of a draft.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

import type { ScreenDocument } from '../model/spec';

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

/** One screen: its draft, versions, schedule, preset pin and resolved working copy. */
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
