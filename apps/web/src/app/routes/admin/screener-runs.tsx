/**
 * `/admin/screener-runs`: the Admin > Screener runs page. The chosen run and the filters live in
 * the URL (`?run=<id>&user=&screener=&status=`).
 */
import { createRoute, useNavigate, useSearch, type AnyRoute } from '@tanstack/react-router';

import { parseFilters, type ScreenerRunFilters } from '@/entities/screener-run';
import { lazyPage } from '@/shared/lib/lazy';

import { pageRoute } from '../page-loader';

const AdminScreenerRunsPage = lazyPage(
  () => import('@/pages/admin-screener-runs'),
  'AdminScreenerRunsPage',
);

interface ScreenerRunsSearch extends ScreenerRunFilters {
  run?: string;
}

export function validateScreenerRunsSearch(search: Record<string, unknown>): ScreenerRunsSearch {
  const { run } = search;
  return { ...(typeof run === 'string' && run ? { run } : {}), ...parseFilters(search) };
}

function ScreenerRunsRoute() {
  const { run, ...filters } = validateScreenerRunsSearch(useSearch({ strict: false }));
  const navigate = useNavigate();
  return (
    <AdminScreenerRunsPage
      selected={run ?? null}
      filters={filters}
      onFiltersChange={(next) => {
        void navigate({
          to: '/admin/screener-runs',
          search: { ...(run ? { run } : {}), ...parseFilters(next) },
          replace: true,
        });
      }}
      onSelect={(id) => {
        void navigate({
          to: '/admin/screener-runs',
          search: { ...filters, run: id },
          replace: true,
        });
      }}
      onClear={() => {
        void navigate({ to: '/admin/screener-runs', search: filters, replace: true });
      }}
    />
  );
}

export function screenerRunsRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'screener-runs',
    validateSearch: validateScreenerRunsSearch,
    ...pageRoute(AdminScreenerRunsPage, (page, client) => {
      page.prefetchScreenerRunsReads(client);
    }),
    component: ScreenerRunsRoute,
  });
}
