/**
 * The writes of the event-study scope list (`PUT` / `DELETE /admin/events/scope/{symbol}`, Admin
 * only; ADR 0050, ADR 0029): add a ticker with an optional note, remove one with an optional
 * note. A name the session's reference cannot resolve is the server's refusal, shown as it is
 * sent. Each write reads the list again.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { refreshEventScope } from '@/entities/event-scope';
import { api, unwrap } from '@/shared/api';

export interface ScopeWrite {
  symbol: string;
  note?: string;
}

export function useAddScopeName() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ symbol, note = '' }: ScopeWrite) =>
      unwrap(
        api.PUT('/admin/events/scope/{symbol}', {
          params: { path: { symbol: symbol.trim() } },
          body: { note: note.trim() },
        }),
      ),
    onSuccess: () => refreshEventScope(client),
  });
}

export function useRemoveScopeName() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ symbol, note = '' }: ScopeWrite) =>
      unwrap(
        api.DELETE('/admin/events/scope/{symbol}', {
          params: {
            path: { symbol },
            ...(note.trim() ? { query: { note: note.trim() } } : {}),
          },
        }),
      ),
    onSuccess: () => refreshEventScope(client),
  });
}
