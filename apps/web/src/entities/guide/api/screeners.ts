/**
 * The Screeners section's reads (ADR 0051, ADR 0037): the lead page (`Query.guideScreenerIndex`)
 * and a family's page (`guideScreenerCategory`), their documents in `screeners-doc.ts`, loaded on
 * first use. One screener's own page is `useGuideScreener` (`hooks.ts`).
 */
import { useQuery } from '@tanstack/react-query';

import { gql, queryKeys } from '@/shared/api';

const GUIDE_STALE_MS = 10 * 60_000;

/** The Screeners lead page: what a screener is and a card per family. */
export function useGuideScreenerIndex() {
  return useQuery({
    queryKey: queryKeys.gql('GuideScreenerIndex', {}),
    queryFn: async ({ queryKey }) => {
      const { GuideScreenerIndexQuery } = await import('./screeners-doc');
      return gql(GuideScreenerIndexQuery, {}, queryKey);
    },
    select: (data) => data.guideScreenerIndex,
    staleTime: GUIDE_STALE_MS,
  });
}

/** One family's page (null data: no such family). */
export function useGuideScreenerCategory(id: string) {
  const variables = { id };
  return useQuery({
    queryKey: queryKeys.gql('GuideScreenerCategory', variables),
    queryFn: async ({ queryKey }) => {
      const { GuideScreenerCategoryQuery } = await import('./screeners-doc');
      return gql(GuideScreenerCategoryQuery, variables, queryKey);
    },
    select: (data) => data.guideScreenerCategory,
    staleTime: GUIDE_STALE_MS,
    retry: false,
  });
}
