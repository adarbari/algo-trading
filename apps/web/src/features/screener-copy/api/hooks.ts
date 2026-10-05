/** Copy a site preset into the user's own screeners (POST /screeners/{name}/copy): pinned to the preset's version. */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { refreshScreens } from '@/entities/screen';
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
