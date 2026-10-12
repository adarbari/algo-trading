/** `/admin/feature-requests`: the Admin › Feature requests page. */
import { createRoute, type AnyRoute } from '@tanstack/react-router';

import { lazyPage } from '@/shared/lib/lazy';

const AdminFeatureRequestsPage = lazyPage(
  () => import('@/pages/admin-feature-requests'),
  'AdminFeatureRequestsPage',
);

export function featureRequestsRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'feature-requests',
    component: AdminFeatureRequestsPage,
  });
}
