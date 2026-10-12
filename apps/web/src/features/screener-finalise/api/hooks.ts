/**
 * Finalise a draft into the next immutable version (POST /screeners/{id}/finalise; a finalised
 * screen runs nightly, ADR 0033) and rebase on a newer preset version (POST .../rebase).
 */
import { useToast } from '@algotrade/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { refreshScreens } from '@/entities/screen';
import { api, queryKeys, unwrap, errorDetail, type components } from '@/shared/api';

export interface FinaliseInput {
  draftSessionId?: string | null;
  choices?: readonly components['schemas']['DraftChoice'][];
}

function useRefresh() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.screeners.all() }),
      refreshScreens(client),
    ]);
}

/**
 * `draftSessionId`: the Describe-it session this screen came from (ADR 0066), if any, and
 * `choices` what the trader decided on its options (sent only with a session).
 */
export function useFinalise(id: string) {
  const refresh = useRefresh();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ draftSessionId, choices = [] }: FinaliseInput) =>
      unwrap(
        api.POST('/screeners/{screener_id}/finalise', {
          params: { path: { screener_id: id } },
          ...(draftSessionId
            ? {
                body: {
                  draft_session_id: draftSessionId,
                  ...(choices.length > 0 ? { choices: [...choices] } : {}),
                },
              }
            : {}),
        }),
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
