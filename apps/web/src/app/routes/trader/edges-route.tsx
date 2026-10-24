/**
 * Trader > Edges: the edges list, or the chosen edge's page (`/edges?edge=momentum_12_1`, so it
 * can be shared and a phone's sheet can be dismissed), and the builder: a new edge
 * (`/edges/new`) or one of the user's own (`/edges/$id/edit`, a copy, a new version or an edge of
 * theirs). The builder loads lazily.
 */
import { createRoute, useNavigate, useSearch } from '@tanstack/react-router';

import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { decodeFilters, filterSearch } from '@/features/filter-bar';
import { lazyPage } from '@/shared/lib/lazy';

const EdgesPage = lazyPage(() => import('@/pages/trader-edges'), 'EdgesPage');
const BuilderRoute = lazyPage(() => import('./edge-builder-route'), 'BuilderRoute');

/**
 * The list's old views (`?view=`) as the filter bar's `f` says them, so a saved link still opens
 * the same narrowing. (The old "rejected" view also held edges the user rejected themselves; the
 * status filter says the site's.)
 */
const LEGACY_VIEWS: Record<string, string> = {
  mine: 'mine:',
  following: 'followed:',
  rejected: 'status:rejected',
};

export interface EdgesSearch {
  edge?: string;
  f?: string;
  q?: string;
}

export function validateEdgesSearch(search: Record<string, unknown>): EdgesSearch {
  const { edge, view, q } = search;
  const legacy = typeof view === 'string' ? LEGACY_VIEWS[view] : undefined;
  const { f } = filterSearch(search.f === undefined && legacy ? { f: legacy } : search);
  return {
    ...(typeof edge === 'string' && edge ? { edge } : {}),
    ...(f ? { f } : {}),
    ...(typeof q === 'string' && q.trim() ? { q } : {}),
  };
}

function EdgesIndex() {
  const search = validateEdgesSearch(useSearch({ strict: false }));
  const navigate = useNavigate();
  return (
    <EdgesPage
      selected={search.edge ?? null}
      search={search}
      onSearchChange={(patch) =>
        void navigate({
          to: '/edges',
          search: (previous) =>
            validateEdgesSearch(
              Object.fromEntries(
                Object.entries({ ...previous, ...patch }).filter(([, v]) => v !== undefined),
              ),
            ),
          replace: true,
        })
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
  loaderDeps: ({ search }) => ({ edge: search.edge ?? null, f: search.f, q: search.q ?? '' }),
  ...pageRoute(
    EdgesPage,
    (page, client, deps: { edge: string | null; f: string | undefined; q: string }) => {
      page.prefetchEdgesReads(client, deps.edge, decodeFilters(deps.f), deps.q);
    },
  ),
  component: EdgesIndex,
});

// The builder: siblings of the list, so `/edges` itself stays one route.
export const edgesBuilderRoutes = [
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'edges/new',
    ...pageRoute(BuilderRoute),
    component: BuilderRoute,
  }),
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'edges/$id/edit',
    ...pageRoute(BuilderRoute),
    component: BuilderRoute,
  }),
];
