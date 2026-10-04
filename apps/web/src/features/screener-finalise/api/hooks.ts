/**
 * Finalise a draft into the next immutable version (POST /screeners/{id}/finalise), switch the
 * nightly schedule on or off (PUT .../schedule: a separate switch), and rebase on a newer preset
 * version (POST .../rebase).
 */
import { useToast } from '@algotrade/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api, queryKeys, unwrap, errorDetail } from '@/shared/api';

function useRefresh() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: queryKeys.screeners.all() });
}

export function useFinalise(id: string) {
  const refresh = useRefresh();
  const toast = useToast();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/screeners/{screener_id}/finalise', { params: { path: { screener_id: id } } }),
      ),
    onSuccess: async (done) => {
      await refresh();
      toast.show({ tone: 'positive', title: `Finalised v${String(done.version)}` });
    },
    onError: (error) => {
      toast.show({
        tone: 'negative',
        title: 'Could not finalise',
        description: errorDetail(error),
      });
    },
  });
}

export function useSetSchedule(id: string) {
  const refresh = useRefresh();
  const toast = useToast();
  return useMutation({
    mutationFn: (schedule: 'nightly' | null) =>
      unwrap(
        api.PUT('/screeners/{screener_id}/schedule', {
          params: { path: { screener_id: id } },
          body: { schedule },
        }),
      ),
    onSuccess: () => refresh(),
    onError: (error) => {
      toast.show({
        tone: 'negative',
        title: 'Could not change the schedule',
        description: errorDetail(error),
      });
    },
  });
}

export function useRebase(id: string) {
  const refresh = useRefresh();
  const toast = useToast();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/screeners/{screener_id}/rebase', { params: { path: { screener_id: id } } }),
      ),
    onSuccess: () => refresh(),
    onError: (error) => {
      toast.show({ tone: 'negative', title: 'Could not rebase', description: errorDetail(error) });
    },
  });
}
