/**
 * Trader > Screeners: the list (`/screeners`), a new screener (`/screeners/new`), a screener's
 * results (`/screeners/$id`, where the list opens; the filter bar's `f` is its search param) and its Builder (`/screeners/$id/edit`).
 * The Builder and a new screener (`screener-builder-routes.tsx`, lazy) may carry
 * `returnTo=<edge id>` (opened from an edge's builder): they then return to it.
 * Tickers open in Explore.
 * The bar's "Test" points here until V9 (Evening Desk plan) moves the flow to `/test`; the
 * `/screeners` list then redirects there.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { filterSearch } from '@/features/filter-bar';
import { compareSearch } from '@/features/idea-compare';
import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { lazyPage } from '@/shared/lib/lazy';

// One import call for both: the entry then carries one preload file list, not two.
const builderRoutes = () => import('./screener-builder-routes');
const NewScreener = lazyPage(builderRoutes, 'NewScreener');
const EditScreener = lazyPage(builderRoutes, 'EditScreener');
const ScreenerResultsPage = lazyPage(
  () => import('@/pages/screener-results'),
  'ScreenerResultsPage',
);
const ScreenersPage = lazyPage(() => import('@/pages/trader-screeners'), 'ScreenersPage');

export const screenersRoute = createRoute({ getParentRoute: () => traderRoute, path: 'screeners' });

/** The list's search params: the filter bar's `f` and the search text `q`. */
export interface ScreenersSearch {
  f?: string;
  q?: string;
}

export function validateScreenersSearch(raw: Record<string, unknown>): ScreenersSearch {
  const { q } = raw;
  return { ...filterSearch(raw), ...(typeof q === 'string' && q.trim() ? { q } : {}) };
}

function ScreenersIndex() {
  const navigate = useNavigate({ from: indexRoute.fullPath });
  const search = indexRoute.useSearch();
  return (
    <ScreenersPage
      search={search}
      onSearchChange={(patch) =>
        void navigate({
          search: (previous) =>
            validateScreenersSearch(
              Object.fromEntries(
                Object.entries({ ...previous, ...patch }).filter(([, v]) => v !== undefined),
              ),
            ),
          replace: true,
        })
      }
      onNew={() => void navigate({ to: '/screeners/new' })}
      onOpen={(id) => void navigate({ to: '/screeners/$id', params: { id } })}
      onEdit={(id) => void navigate({ to: '/screeners/$id/edit', params: { id } })}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
    />
  );
}

function ScreenerResultsRoute() {
  const { id } = resultsRoute.useParams();
  const { f } = resultsRoute.useSearch();
  const navigate = useNavigate({ from: resultsRoute.fullPath });
  return (
    <ScreenerResultsPage
      id={id}
      f={f}
      onFilterChange={(next) => void navigate({ search: next ? { f: next } : {}, replace: true })}
      onEdit={() => void navigate({ to: '/screeners/$id/edit', params: { id } })}
      onOpenTicker={(symbol) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })
      }
      onCompare={(symbols) => {
        const search = compareSearch(symbols);
        if (search) void navigate({ to: '/explore', search });
      }}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
    />
  );
}

const indexRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: '/',
  validateSearch: validateScreenersSearch,
  loaderDeps: ({ search }) => ({ f: search.f, q: search.q ?? '' }),
  ...pageRoute(ScreenersPage, (page, client, deps: { f: string | undefined; q: string }) => {
    page.prefetchScreenersReads(client, deps.f, deps.q);
  }),
  component: ScreenersIndex,
});
const newRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: 'new',
  ...pageRoute(NewScreener),
  component: NewScreener,
});
const resultsRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: '$id',
  validateSearch: filterSearch,
  ...pageRoute(ScreenerResultsPage),
  component: ScreenerResultsRoute,
});
const editRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: '$id/edit',
  ...pageRoute(EditScreener),
  component: EditScreener,
});

export const screenersRoutes = screenersRoute.addChildren([
  indexRoute,
  newRoute,
  resultsRoute,
  editRoute,
]);
