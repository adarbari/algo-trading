/**
 * `/admin/screener-runs`: the Admin > Screener runs page. The chosen run and the filters live in
 * the URL (`?run=<id>&user=&screener=&status=`).
 */
import { createRoute, useNavigate, useSearch, type AnyRoute } from '@tanstack/react-router';

import { lazyPage } from '@/shared/lib/lazy';

import { pageRoute } from '../page-loader';

const AdminScreenerRunsPage = lazyPage(
  () => import('@/pages/admin-screener-runs'),
  'AdminScreenerRunsPage',
);

function ScreenerRunsRoute() {
  const search = useSearch({ strict: false });
  const navigate = useNavigate();
  return (
    <AdminScreenerRunsPage
      search={search}
      onChange={(next) => void navigate({ to: '.', search: next, replace: true })}
    />
  );
}

export function screenerRunsRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'screener-runs',
    ...pageRoute(AdminScreenerRunsPage),
    component: ScreenerRunsRoute,
  });
}
