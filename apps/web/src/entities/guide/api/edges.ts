/**
 * The Edges section's reads (ADR 0051, ADR 0037): `Query.guideEdgeIndex` (the index's own query)
 * and a mechanism's and a site edge's page (`guideMechanism`, `guideEdge`), their documents in
 * `edges-doc.ts`, loaded on first use. Kept in its own module, so only the Edges pages and the two
 * help drawers, which load on demand, carry it.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, queryKeys } from '@/shared/api';

const GUIDE_STALE_MS = 10 * 60_000;

/** The Edges section's top page: mechanism cards, filters, edges set aside, ideas not built. */
export function useGuideEdgeIndex({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.gql('GuideEdgeIndex', {}),
    queryFn: async () => {
      const { GuideEdgeIndexQuery } = await import('./edges-doc');
      return gql(GuideEdgeIndexQuery, {});
    },
    select: (data) => data.guideEdgeIndex,
    enabled,
    staleTime: GUIDE_STALE_MS,
  });
}

/** One mechanism's page (null data: no such mechanism). */
export function useGuideMechanism(id: string) {
  const variables = { id };
  return useQuery({
    queryKey: queryKeys.gql('GuideMechanism', variables),
    queryFn: async () => {
      const { GuideMechanismQuery } = await import('./edges-doc');
      return gql(GuideMechanismQuery, variables);
    },
    select: (data) => data.guideMechanism,
    staleTime: GUIDE_STALE_MS,
    retry: false,
  });
}

/** One site edge's Guide page (null data: no such edge). */
export function useGuideEdge(id: string) {
  const variables = { id };
  return useQuery({
    queryKey: queryKeys.gql('GuideEdge', variables),
    queryFn: async () => {
      const { GuideEdgeQuery } = await import('./edges-doc');
      return gql(GuideEdgeQuery, variables);
    },
    select: (data) => data.guideEdge,
    staleTime: GUIDE_STALE_MS,
    retry: false,
  });
}
