/** `/admin/feature-requests`: the Admin › Feature requests page. The status filter lives in the URL (`?status=OPEN`). */
import { createRoute, useNavigate, useSearch, type AnyRoute } from '@tanstack/react-router';

import { lazyPage } from '@/shared/lib/lazy';

const AdminFeatureRequestsPage = lazyPage(
  () => import('@/pages/admin-feature-requests'),
  'AdminFeatureRequestsPage',
);

interface FeatureRequestsSearch {
  status?: string;
}

export function validateFeatureRequestsSearch(
  search: Record<string, unknown>,
): FeatureRequestsSearch {
  const { status } = search;
  return typeof status === 'string' && status ? { status } : {};
}

function FeatureRequestsRoute() {
  const { status } = validateFeatureRequestsSearch(useSearch({ strict: false }));
  const navigate = useNavigate();
  return (
    <AdminFeatureRequestsPage
      status={status ?? null}
      onStatusChange={(next) => {
        void navigate({
          to: '/admin/feature-requests',
          search: next ? { status: next } : {},
          replace: true,
        });
      }}
    />
  );
}

export function featureRequestsRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'feature-requests',
    validateSearch: validateFeatureRequestsSearch,
    component: FeatureRequestsRoute,
  });
}
