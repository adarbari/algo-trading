/**
 * Trader > Ideas: the route validates the search params (the column set and the filter bar's `f`,
 * so a view of the table is a shareable link) and hands them to the page with a setter that
 * replaces the URL. Tickers open in Explore, one or as a compare set (Explore's search params,
 * a single ticker with `via`, the screener that surfaced it); a screener chip opens that
 * screener's results.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { filterSearch } from '@/features/filter-bar';
import { parseIdeasSearch, type IdeaTab } from '@/entities/idea';
import type { TopIdeasSearch, TopIdeasSearchPatch } from '@/widgets/top-ideas';

import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { lazyPage } from '@/shared/lib/lazy';

const IdeasPage = lazyPage(() => import('@/pages/trader-ideas'), 'IdeasPage');

/** The page's chunks load in the loader (so the page renders unsuspended) and its reads start
 * with them, not when the widgets mount; the hooks join the requests in flight. */
const loading = pageRoute(IdeasPage, (page, client, deps: { tab: IdeaTab | undefined }) => {
  page.prefetchIdeasReads(client, deps.tab);
});

/** The search params after a patch: `undefined` removes a key. */
function patched(previous: TopIdeasSearch, patch: TopIdeasSearchPatch): TopIdeasSearch {
  const merged: Record<string, unknown> = { ...previous, ...patch };
  return validateSearch(
    Object.fromEntries(Object.entries(merged).filter(([, value]) => value !== undefined)),
  );
}

/** The page's own params (the column set) and the filter bar's `f`. */
function validateSearch(raw: Record<string, unknown>): TopIdeasSearch {
  return { ...parseIdeasSearch(raw), ...filterSearch(raw) };
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
  validateSearch,
  loaderDeps: ({ search }) => ({ tab: search.tab }),
  ...loading,
  component: IdeasRoute,
});
