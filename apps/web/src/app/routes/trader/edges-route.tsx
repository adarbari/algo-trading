/**
 * Trader > Edges: the edges list, or the chosen edge's page (`/edges?edge=momentum_12_1`, so it
 * can be shared and a phone's sheet can be dismissed), and the builder: a new edge
 * (`/edges/new`) or one of the user's own (`/edges/$id/edit`, a copy, a new version or an edge of
 * theirs). The builder loads lazily; `?screen=<id>` is the screen just edited or made in the
 * Screen Builder, added to the draft.
 */
import { createRoute, useNavigate, useSearch } from '@tanstack/react-router';

import { traderRoute } from './layout-route';
import { NEW_EDGE } from './return-to-edge';
import type { EdgeView } from '@/entities/edge';
import { lazyPage } from '@/shared/lib/lazy';

const EdgesPage = lazyPage(() => import('@/pages/trader-edges'), 'EdgesPage');
const EdgeBuilderPage = lazyPage(() => import('@/pages/edge-builder'), 'EdgeBuilderPage');

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

interface BuilderSearch {
  screen?: string;
}

export function validateBuilderSearch(search: Record<string, unknown>): BuilderSearch {
  const { screen } = search;
  return typeof screen === 'string' && screen ? { screen } : {};
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
      onEdit={(id) => void navigate({ to: '/edges/$id/edit', params: { id } })}
      onNew={() => void navigate({ to: '/edges/new' })}
      onClear={() => void navigate({ to: '/edges', search: {}, replace: true })}
    />
  );
}

function Builder({ id, screen }: { id: string | null; screen: string | undefined }) {
  const navigate = useNavigate();
  return (
    <EdgeBuilderPage
      id={id}
      addScreen={screen}
      onCancel={() => void navigate({ to: '/edges', search: id ? { edge: id } : {} })}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
      onOpenScreen={(screenId, from) => {
        const search = { returnTo: from ?? NEW_EDGE };
        if (screenId === null) void navigate({ to: '/screeners/new', search });
        else void navigate({ to: '/screeners/$id/edit', params: { id: screenId }, search });
      }}
    />
  );
}

function NewEdge() {
  return <Builder id={null} screen={newRoute.useSearch().screen} />;
}

function EditEdge() {
  return <Builder id={editRoute.useParams().id} screen={editRoute.useSearch().screen} />;
}

export const edgesRoute = createRoute({ getParentRoute: () => traderRoute, path: 'edges' });

const indexRoute = createRoute({
  getParentRoute: () => edgesRoute,
  path: '/',
  validateSearch: validateEdgesSearch,
  component: EdgesIndex,
});
const newRoute = createRoute({
  getParentRoute: () => edgesRoute,
  path: 'new',
  validateSearch: validateBuilderSearch,
  component: NewEdge,
});
const editRoute = createRoute({
  getParentRoute: () => edgesRoute,
  path: '$id/edit',
  validateSearch: validateBuilderSearch,
  component: EditEdge,
});

export const edgesRoutes = edgesRoute.addChildren([indexRoute, newRoute, editRoute]);
