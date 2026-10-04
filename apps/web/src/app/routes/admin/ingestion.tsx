/**
 * `/admin/ingestion`: the Admin › Ingestion page. The drilled-into cell lives in the URL
 * (`?dataset=bars/1d&session=2026-10-02`) so a drill-down can be shared; both or neither.
 */
import { createRoute, useNavigate, useSearch, type AnyRoute } from '@tanstack/react-router';

import type { CellRef } from '@/entities/ingestion';
import { AdminIngestionPage } from '@/pages/admin-ingestion';

interface IngestionSearch {
  dataset?: string;
  session?: string;
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export function validateIngestionSearch(search: Record<string, unknown>): IngestionSearch {
  const { dataset, session } = search;
  if (
    typeof dataset === 'string' &&
    dataset &&
    typeof session === 'string' &&
    ISO_DAY.test(session)
  ) {
    return { dataset, session };
  }
  return {};
}

function IngestionRoute() {
  const { dataset, session } = validateIngestionSearch(useSearch({ strict: false }));
  const navigate = useNavigate();
  const selected: CellRef | null = dataset && session ? { dataset, session } : null;
  return (
    <AdminIngestionPage
      selected={selected}
      onSelectCell={(cell) => {
        void navigate({ to: '/admin/ingestion', search: { ...cell }, replace: true });
      }}
    />
  );
}

export function ingestionRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'ingestion',
    validateSearch: validateIngestionSearch,
    component: IngestionRoute,
  });
}
