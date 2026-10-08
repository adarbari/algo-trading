/**
 * Trader > Edges: the edges list beside the chosen edge's detail. The chosen edge lives in the
 * URL (`/edges?edge=momentum_12_1`) so it can be shared and a phone's sheet can be dismissed.
 */
import { createRoute, useNavigate, useSearch } from '@tanstack/react-router';

import { EdgesPage } from '@/pages/trader-edges';

import { traderRoute } from './layout-route';

interface EdgesSearch {
  edge?: string;
}

export function validateEdgesSearch(search: Record<string, unknown>): EdgesSearch {
  const { edge } = search;
  return typeof edge === 'string' && edge ? { edge } : {};
}

function EdgesRoute() {
  const { edge } = validateEdgesSearch(useSearch({ strict: false }));
  const navigate = useNavigate();
  return (
    <EdgesPage
      selected={edge ?? null}
      onSelect={(id) => void navigate({ to: '/edges', search: { edge: id }, replace: true })}
      onClear={() => void navigate({ to: '/edges', search: {}, replace: true })}
    />
  );
}

export const edgesRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'edges',
  validateSearch: validateEdgesSearch,
  component: EdgesRoute,
});
