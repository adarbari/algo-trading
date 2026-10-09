/**
 * Trader > Edges: the edges list, or the chosen edge's page. The chosen edge lives in the
 * URL (`/edges?edge=momentum_12_1`) so it can be shared and a phone's sheet can be dismissed.
 */
import { createRoute, useNavigate, useSearch } from '@tanstack/react-router';

import { traderRoute } from './layout-route';
import type { EdgeView } from '@/entities/edge';
import { lazyPage } from '@/shared/lib/lazy';

const EdgesPage = lazyPage(() => import('@/pages/trader-edges'), 'EdgesPage');

// The views a link may name (`all` is the bare list); a type import only keeps the entity out of
// the entry chunk.
const VIEWS: readonly EdgeView[] = ['mine', 'following', 'rejected'];

interface EdgesSearch {
  edge?: string;
  view?: EdgeView;
}

export function validateEdgesSearch(search: Record<string, unknown>): EdgesSearch {
  const { edge, view } = search;
  const found = VIEWS.find((v) => v === view);
  return {
    ...(typeof edge === 'string' && edge ? { edge } : {}),
    ...(found ? { view: found } : {}),
  };
}

function EdgesRoute() {
  const { edge, view } = validateEdgesSearch(useSearch({ strict: false }));
  const navigate = useNavigate();
  return (
    <EdgesPage
      selected={edge ?? null}
      {...(view ? { view } : {})}
      onViewChange={(next) =>
        void navigate({ to: '/edges', search: next === 'all' ? {} : { view: next }, replace: true })
      }
      onSelect={(id) => void navigate({ to: '/edges', search: { edge: id }, replace: true })}
      onClear={() => void navigate({ to: '/edges', search: {}, replace: true })}
    />
  );
}

export const edgesRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'edges',
  validateSearch: validateEdgesSearch,
  component: EdgesRoute,
});
