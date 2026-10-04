/** Formula features: the type check with sample values (POST /features/check) and saving a named one (POST /features/user). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

/** How many sample values the check returns. */
const SAMPLE_ROWS = 5;

/** The check of a formula as typed (the caller debounces `expr`); an invalid one is an error naming the position. */
export function useFormulaCheck(expr: string) {
  const text = expr.trim();
  return useQuery({
    queryKey: queryKeys.features.check(text),
    queryFn: () =>
      unwrap(api.POST('/features/check', { body: { expr: text, sample: SAMPLE_ROWS } })),
    enabled: text !== '',
    retry: false,
    staleTime: 60_000,
  });
}

export interface FormulaFeatureInput {
  name: string;
  expr: string;
  dtype: string;
  unit: string;
  description: string;
  null_meaning: string;
}

/** Saves the user's feature and refreshes the catalogue so the picker offers it. */
export function useSaveFormulaFeature() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: FormulaFeatureInput) =>
      unwrap(api.POST('/features/user', { body: { ...body, theme: 'builder' } })),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.features.catalogue() }),
  });
}
