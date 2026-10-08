/**
 * Saving the user's train / test split: `PUT /evaluation/split` (`split_from`: a stored
 * session, or null to clear). Once saved, the split read is refetched; the API's refusal (a date
 * outside the stored sessions) is the form's error.
 */
import { refreshEvaluationSplit } from '@/entities/edge';
import { api, unwrap } from '@/shared/api';
import { useMutation, useQueryClient } from '@tanstack/react-query';

/** `splitFrom`: the first session of the test slice (YYYY-MM-DD), or null to clear it. */
export function useSaveSplit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (splitFrom: string | null) =>
      unwrap(api.PUT('/evaluation/split', { body: { split_from: splitFrom } })),
    onSuccess: () => refreshEvaluationSplit(client),
  });
}
