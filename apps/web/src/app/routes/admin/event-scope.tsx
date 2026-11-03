/** `/admin/event-scope`: the Admin › Event scope page. */
import { createRoute, type AnyRoute } from '@tanstack/react-router';

import { lazyPage } from '@/shared/lib/lazy';

import { pageRoute } from '../page-loader';

const AdminEventScopePage = lazyPage(
  () => import('@/pages/admin-event-scope'),
  'AdminEventScopePage',
);

export function eventScopeRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'event-scope',
    ...pageRoute(AdminEventScopePage),
    component: AdminEventScopePage,
  });
}
