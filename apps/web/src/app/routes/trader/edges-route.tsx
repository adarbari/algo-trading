/**
 * Trader > Edges: the edges list, or the chosen edge's page (`/edges?edge=momentum_12_1`, so it
 * can be shared and a phone's sheet can be dismissed). The builder is part of the Test flow
 * (`/test/setup`); `/edges/new` and `/edges/$id/edit` redirect there (`redirects.ts`).
 */
import { createRoute, useNavigate, useSearch } from '@tanstack/react-router';

import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { filterSearch } from '@/features/filter-bar';
import { lazyPage } from '@/shared/lib/lazy';

const EdgesPage = lazyPage(() => import('@/pages/trader-edges'), 'EdgesPage');

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
        void navigate(id ? { to: '/test/setup/$id', params: { id } } : { to: '/test/setup' })
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
      page.prefetchEdgesReads(client, deps.edge, deps.f, deps.q);
    },
  ),
  component: EdgesIndex,
});
