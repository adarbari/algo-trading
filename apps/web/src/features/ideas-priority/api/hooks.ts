/**
 * Saving the screener priority: PUT /preferences/ideas, optimistic. The list reorders at once
 * (the cached `IdeasPage` responses take the new order); on a failure the previous cache is
 * restored and a toast says so; once settled the ideas are refetched, ranked by the server in
 * the saved order.
 */
import { useToast } from '@algotrade/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { IDEAS_OPERATION, type IdeasResponse } from '@/entities/idea';
import { api, queryKeys, unwrap } from '@/shared/api';

import { withPriority } from '../model/priority';

const IDEAS = queryKeys.gqlAll(IDEAS_OPERATION);

type Snapshot = [readonly unknown[], IdeasResponse | undefined][];

export function useSavePriority() {
  const client = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (priority: string[]) =>
      unwrap(api.PUT('/preferences/ideas', { body: { priority } })),
    onMutate: async (priority): Promise<{ previous: Snapshot }> => {
      await client.cancelQueries({ queryKey: IDEAS });
      const previous = client.getQueriesData<IdeasResponse>({ queryKey: IDEAS });
      client.setQueriesData<IdeasResponse>({ queryKey: IDEAS }, (cached) =>
        cached ? withPriority(cached, priority) : cached,
      );
      return { previous };
    },
    onError: (_error, _priority, context) => {
      for (const [key, data] of context?.previous ?? []) client.setQueryData(key, data);
      toast.show({
        tone: 'negative',
        title: 'Could not save the screener order',
        description: 'The previous order is back. Try again.',
      });
    },
    onSettled: () => client.invalidateQueries({ queryKey: IDEAS }),
  });
}
