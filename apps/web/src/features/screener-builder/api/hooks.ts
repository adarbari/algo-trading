/**
 * Writes of the draft: save (PUT /screeners/{id}/draft), discard (DELETE), and create a blank
 * draft for a new screener. Each refreshes the screen's detail so the Builder re-reads the server.
 */
import { useToast } from '@algotrade/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import type { ScreenDocument } from '@/entities/screen';
import { api, ApiError, queryKeys, unwrap, errorDetail } from '@/shared/api';

/** Refresh everything cached about one screen. */
function useRefresh(id: string) {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.screeners.detail(id) }),
      client.invalidateQueries({ queryKey: queryKeys.screeners.versions(id) }),
      client.invalidateQueries({ queryKey: queryKeys.screeners.list() }),
    ]);
}

export function useSaveDraft(id: string) {
  const refresh = useRefresh(id);
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
  const refresh = useRefresh(id);
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
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.screeners.all() }),
  });
}
