/**
 * The edge builder's route component, loaded on first visit (`/edges/new`, `/edges/$id/edit`):
 * it and its navigation live here, outside the entry chunk. Cancel goes back; opening a
 * screen sends the Screen Builder `returnTo` (the edge's id, `NEW_EDGE` before it is saved) so it
 * offers "Save and return to edge".
 */
import { useNavigate, useParams, useRouter } from '@tanstack/react-router';

import { EdgeBuilderPage } from '@/pages/edge-builder';

import { NEW_EDGE } from './return-to-edge';

export function BuilderRoute() {
  const { id } = useParams({ strict: false });
  const navigate = useNavigate();
  const router = useRouter();
  return (
    <EdgeBuilderPage
      id={id ?? null}
      onCancel={() => {
        router.history.back();
      }}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
      onOpenScreen={(screenId, from) => {
        const search = { returnTo: from ?? NEW_EDGE };
        if (screenId === null) void navigate({ to: '/screeners/new', search });
        else void navigate({ to: '/screeners/$id/edit', params: { id: screenId }, search });
      }}
    />
  );
}
