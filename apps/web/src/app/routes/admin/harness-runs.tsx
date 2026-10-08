/** `/admin/harness-runs`: the Admin > Harness runs page. The chosen run lives in the URL (`?run=<id>`). */
import { createRoute, useNavigate, useSearch, type AnyRoute } from '@tanstack/react-router';

import { AdminHarnessRunsPage } from '@/pages/admin-harness-runs';

interface HarnessRunsSearch {
  run?: string;
}

export function validateHarnessRunsSearch(search: Record<string, unknown>): HarnessRunsSearch {
  const { run } = search;
  return typeof run === 'string' && run ? { run } : {};
}

function HarnessRunsRoute() {
  const { run } = validateHarnessRunsSearch(useSearch({ strict: false }));
  const navigate = useNavigate();
  return (
    <AdminHarnessRunsPage
      selected={run ?? null}
      onSelect={(id) => {
        void navigate({ to: '/admin/harness-runs', search: { run: id }, replace: true });
      }}
      onClear={() => {
        void navigate({ to: '/admin/harness-runs', search: {}, replace: true });
      }}
    />
  );
}

export function harnessRunsRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'harness-runs',
    validateSearch: validateHarnessRunsSearch,
    component: HarnessRunsRoute,
  });
}
