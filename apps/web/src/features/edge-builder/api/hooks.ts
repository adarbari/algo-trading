/**
 * Save the user's edge (`PUT /edges/{id}`): the whole document, which the API checks as the
 * harness will read it and writes only if it loads (a refusal is the message). Reads the edges
 * again.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { refreshEdges } from '@/entities/edge';
import { api, unwrap } from '@/shared/api';

export function useSaveEdge() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, document }: { id: string; document: Record<string, unknown> }) =>
      unwrap(
        api.PUT('/edges/{edge_id}', { params: { path: { edge_id: id } }, body: { document } }),
      ),
    onSuccess: () => refreshEdges(client),
  });
}
