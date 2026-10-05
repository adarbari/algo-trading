/**
 * Writes of the draft: save (PUT /screeners/{id}/draft), discard (DELETE), and create a blank
 * draft for a new screener. Each refreshes the screen's detail so the Builder re-reads the server.
 */
import { useToast } from '@algotrade/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { refreshScreens, type ScreenDocument } from '@/entities/screen';
import { api, ApiError, queryKeys, unwrap, errorDetail } from '@/shared/api';

/** Refresh everything cached about the screens (lists, detail, versions). */
function useRefresh() {
  const client = useQueryClient();
  return () => refreshScreens(client);
}

export function useSaveDraft(id: string) {
  const refresh = useRefresh();
  const toast = useToast();
  return useMutation({
    mutationFn: (document: ScreenDocument) =>
      unwrap(
        api.PUT('/screeners/{screener_id}/draft', {
          params: { path: { screener_id: id } },
          body: { document },
        }),
      ),
    onSuccess: () => refresh(),
    onError: (error) => {
      toast.show({
        tone: 'negative',
        title: 'Could not save the draft',
        description: errorDetail(error),
      });
    },
  });
}

export function useDiscardDraft(id: string) {
  const refresh = useRefresh();
  const toast = useToast();
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE('/screeners/{screener_id}/draft', {
        params: { path: { screener_id: id } },
      });
      if (error !== undefined) throw new ApiError(response.status, response.statusText);
    },
    onSuccess: () => refresh(),
    onError: (error) => {
      toast.show({
        tone: 'negative',
        title: 'Could not discard the draft',
        description: errorDetail(error),
      });
    },
  });
}

/**
 * Makes the user's copy of the site preset `id` (POST /screeners/{id}/copy, pinned to its current
 * version) as a draft of the same name: the first edit of a preset does it, transparently.
 */
export function useCopyOwnPreset(id: string) {
  const refresh = useRefresh();
  const toast = useToast();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/screeners/{screener_id}/copy', {
          params: { path: { screener_id: id } },
          body: { preset: id },
        }),
      ),
    onSuccess: () => refresh(),
    onError: (error) => {
      toast.show({
        tone: 'negative',
        title: 'Could not make your copy',
        description: errorDetail(error),
      });
    },
  });
}

/** Starts a screener: a blank draft saved under its id (then the Builder opens it). */
export function useCreateScreener() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, document }: { id: string; document: ScreenDocument }) =>
      unwrap(
        api.PUT('/screeners/{screener_id}/draft', {
          params: { path: { screener_id: id } },
          body: { document },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.screeners.all() }),
        refreshScreens(client),
      ]),
  });
}
