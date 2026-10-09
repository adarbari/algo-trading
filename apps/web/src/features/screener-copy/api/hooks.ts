/**
 * Copy a screener into the user's own: a site preset (POST /screeners/{name}/copy, pinned to the
 * preset's version) or one of their own (the source's document saved as a draft under the new
 * name, PUT /screeners/{name}/draft; a copy of a copy keeps its `extends` link to the preset).
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import {
  refreshScreens,
  toDocument,
  useScreener,
  useScreenerVersions,
  type ScreenDocument,
} from '@/entities/screen';
import { api, queryKeys, unwrap } from '@/shared/api';

export function useCopyPreset(preset: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(
        api.POST('/screeners/{screener_id}/copy', {
          params: { path: { screener_id: name } },
          body: { preset },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.screeners.all() }),
        refreshScreens(client),
      ]),
  });
}

/** The document of one of the user's screens: its draft, else its newest finalized version. */
export function useSourceDocument(id: string, enabled: boolean) {
  const detail = useScreener(enabled ? id : null);
  const versions = useScreenerVersions(id, enabled);
  const source = detail.data?.draft ?? versions.data?.at(-1)?.document ?? null;
  return { document: source, isError: detail.isError || versions.isError };
}

export function useDuplicateScreener() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, source }: { name: string; source: Record<string, unknown> }) => {
      const document: ScreenDocument = toDocument(source, name);
      return unwrap(
        api.PUT('/screeners/{screener_id}/draft', {
          params: { path: { screener_id: name } },
          body: { document },
        }),
      );
    },
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.screeners.all() }),
        refreshScreens(client),
      ]),
  });
}
