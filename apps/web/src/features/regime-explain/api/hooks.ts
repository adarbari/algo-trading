/**
 * The regime explanation POSTs (`POST /regime/explain`, ADR 0041 amended). `useExplainRegime`
 * asks for one explanation (the fixed question, or a card's key); nothing is asked of the model
 * unless the user clicks. `useExplainAvailable` learns whether a text model is configured
 * without calling it: an empty body is answered 503 when `llm.toml` has no model and 400
 * ("ask one of question or card") when it has, before the model or the rate limit is touched.
 */
import { useMutation, useQuery } from '@tanstack/react-query';

import { api, ApiError, unwrap, type components } from '@/shared/api';

export type RegimeExplanation = components['schemas']['RegimeExplanation'];

/** The one question the API accepts besides a card key. */
export const WHAT_IS_HAPPENING = 'what is happening?';

/** The route's own 400 for a body that asks for nothing (any other 400 is not the probe's). */
export const PROBE_ANSWER = 'ask one of question or card';

export interface ExplainAsk {
  /** A card key of the regime, or `undefined` for "what is happening?". */
  card?: string | undefined;
}

export const AVAILABLE_KEY = ['regime-explain', 'available'] as const;

export function useExplainAvailable() {
  return useQuery({
    queryKey: AVAILABLE_KEY,
    queryFn: async (): Promise<boolean> => {
      try {
        await unwrap(api.POST('/regime/explain', { body: { question: null, card: null } }));
        return true;
      } catch (error) {
        if (error instanceof ApiError && error.status === 400 && error.detail === PROBE_ANSWER) {
          return true;
        }
        if (error instanceof ApiError && error.status === 503) return false;
        throw error;
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useExplainRegime() {
  return useMutation({
    mutationFn: ({ card }: ExplainAsk) =>
      unwrap(
        api.POST('/regime/explain', {
          body: card === undefined ? { question: WHAT_IS_HAPPENING, card: null } : { card },
        }),
      ),
  });
}
