/**
 * Delete one of the user's screeners (DELETE /screeners/{id}): the API archives its draft and
 * every version, so it leaves the list and the nightly; its past runs stay.
 */
import { useToast } from '@algotrade/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api, ApiError, errorDetail, queryKeys } from '@/shared/api';

export function useDeleteScreener(id: string) {
  const client = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE('/screeners/{screener_id}', {
        params: { path: { screener_id: id } },
      });
      if (error !== undefined) throw new ApiError(response.status, response.statusText);
    },
    onSuccess: () => {
      // Drop the screen's own entries (they would answer 404 now), then refresh the lists.
      client.removeQueries({ queryKey: queryKeys.screeners.detail(id) });
      void client.invalidateQueries({ queryKey: queryKeys.screeners.all() });
      toast.show({ tone: 'positive', title: `Deleted ${id}` });
    },
    onError: (error) => {
      toast.show({
        tone: 'negative',
        title: 'Could not delete the screener',
        description: errorDetail(error),
      });
    },
  });
}
