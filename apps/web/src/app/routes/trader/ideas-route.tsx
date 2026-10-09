/**
 * Trader > Ideas: the route validates the search params (the view in use and the filter chips,
 * so a view of the table is a shareable link) and hands them to the page with a setter that
 * replaces the URL. Tickers open in Explore, one or as a compare set (Explore's search params,
 * a single ticker with `via`, the screener that surfaced it); a screener chip opens that
 * screener's results.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { parseIdeasSearch, type IdeasSearch, type IdeasSearchPatch } from '@/entities/idea';

import { traderRoute } from './layout-route';
import { lazyPage } from '@/shared/lib/lazy';

const IdeasPage = lazyPage(() => import('@/pages/trader-ideas'), 'IdeasPage');

/** The search params after a patch: `undefined` removes a key. */
function patched(previous: IdeasSearch, patch: IdeasSearchPatch): IdeasSearch {
  const merged: Record<string, unknown> = { ...previous, ...patch };
  return parseIdeasSearch(
    Object.fromEntries(Object.entries(merged).filter(([, value]) => value !== undefined)),
  );
}

function IdeasRoute() {
  const search = ideasRoute.useSearch();
  const navigate = useNavigate({ from: ideasRoute.fullPath });
  return (
    <IdeasPage
      search={search}
      onSearchChange={(patch) =>
        void navigate({ search: (previous) => patched(previous, patch), replace: true })
      }
      onCompare={(compare) => void navigate({ to: '/explore', search: compare })}
      onScreeners={() => void navigate({ to: '/screeners' })}
      onOpenRegime={() => void navigate({ to: '/regime' })}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
      onOpenEdges={() => void navigate({ to: '/edges' })}
      onOpenScreener={(id) => void navigate({ to: '/screeners/$id', params: { id } })}
      onOpen={(symbol, via) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol, via } })
      }
    />
  );
}

export const ideasRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'ideas',
  validateSearch: parseIdeasSearch,
  component: IdeasRoute,
});
