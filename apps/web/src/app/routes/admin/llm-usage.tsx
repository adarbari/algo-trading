/**
 * `/admin/llm-usage`: the Admin › LLM usage & cost page. The chosen call lives in the URL
 * (`?call=<id>`) so a drill-down can be shared.
 */
import { createRoute, useNavigate, useSearch, type AnyRoute } from '@tanstack/react-router';

import { lazyPage } from '../lazy-page';

const AdminLlmUsagePage = lazyPage(() => import('@/pages/admin-llm-usage'), 'AdminLlmUsagePage');

interface LlmUsageSearch {
  call?: string;
}

export function validateLlmUsageSearch(search: Record<string, unknown>): LlmUsageSearch {
  const { call } = search;
  return typeof call === 'string' && call ? { call } : {};
}

function LlmUsageRoute() {
  const { call } = validateLlmUsageSearch(useSearch({ strict: false }));
  const navigate = useNavigate();
  return (
    <AdminLlmUsagePage
      selected={call ?? null}
      onSelectCall={(id) => {
        void navigate({ to: '/admin/llm-usage', search: { call: id }, replace: true });
      }}
      onClearCall={() => {
        void navigate({ to: '/admin/llm-usage', search: {}, replace: true });
      }}
    />
  );
}

export function llmUsageRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'llm-usage',
    validateSearch: validateLlmUsageSearch,
    component: LlmUsageRoute,
  });
}
