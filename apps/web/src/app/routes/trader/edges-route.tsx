/**
 * Trader > Edges: the edges list, or the chosen edge's page (`/edges?edge=momentum_12_1`, so it
 * can be shared and a phone's sheet can be dismissed), and the builder: a new edge
 * (`/edges/new`) or one of the user's own (`/edges/$id/edit`, a copy, a new version or an edge of
 * theirs). The builder loads lazily.
 */
import { createRoute, useNavigate, useSearch } from '@tanstack/react-router';

import { traderRoute } from './layout-route';
import type { EdgeView } from '@/entities/edge';
import { lazyPage } from '@/shared/lib/lazy';

const EdgesPage = lazyPage(() => import('@/pages/trader-edges'), 'EdgesPage');
const BuilderRoute = lazyPage(() => import('./edge-builder-route'), 'BuilderRoute');

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

function EdgesIndex() {
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
      onBuild={(id) =>
        void navigate(id ? { to: '/edges/$id/edit', params: { id } } : { to: '/edges/new' })
      }
      onClear={() => void navigate({ to: '/edges', search: {}, replace: true })}
    />
  );
}

export const edgesRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'edges',
  validateSearch: validateEdgesSearch,
  component: EdgesIndex,
});

// The builder: siblings of the list, so `/edges` itself stays one route.
export const edgesBuilderRoutes = [
  createRoute({ getParentRoute: () => traderRoute, path: 'edges/new', component: BuilderRoute }),
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'edges/$id/edit',
    component: BuilderRoute,
  }),
];
