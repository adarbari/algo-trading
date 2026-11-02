/**
 * Trader > Ideas: the route validates the search params (the column set and the filter bar's `f`,
 * so a view of the table is a shareable link) and hands them to the page with a setter that
 * replaces the URL. Tickers open in Explore, one or as a compare set (Explore's search params,
 * a single ticker with `via`, the screener that surfaced it); a screener chip opens that
 * screener's results. The idea page (`/ideas/$symbol?setup=`) is the second route here: it
 * validates the one search param (the setup shown; absent: the best that picked the name); back
 * goes to Ideas on the name's tab, a name opens in Explore with the setup's screener.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { filterSearch } from '@/features/filter-bar';
import { parseIdeasSearch, type IdeaTab } from '@/entities/idea';
import type { TopIdeasSearch, TopIdeasSearchPatch } from '@/widgets/top-ideas';

import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { lazyPage } from '@/shared/lib/lazy';

const IdeasPage = lazyPage(() => import('@/pages/trader-ideas'), 'IdeasPage');
const IdeaPage = lazyPage(() => import('@/pages/trader-idea'), 'IdeaPage');

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
      onOpenIdea={(symbol, setup) =>
        void navigate({ to: '/ideas/$symbol', params: { symbol }, search: { setup } })
      }
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

const idea = pageRoute(IdeaPage);


function validateIdeaSearch(raw: Record<string, unknown>): { setup?: string } {
  return typeof raw['setup'] === 'string' && raw['setup'] !== '' ? { setup: raw['setup'] } : {};
}

function IdeaRoute() {
  const { symbol } = ideaRoute.useParams();
  const { setup } = ideaRoute.useSearch();
  const navigate = useNavigate({ from: ideaRoute.fullPath });
  return (
    <IdeaPage
      symbol={symbol}
      setup={setup}
      onSetupChange={(edge) => void navigate({ search: { setup: edge }, replace: true })}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
      onOpenTicker={(sel) =>
        void navigate({ to: '/explore', search: { sel, focus: sel, via: setup ?? '' } })
      }
      onBack={(tab) =>
        void navigate({ to: '/ideas', search: tab === 'premium' ? { tab: 'premium' } : {} })
      }
    />
  );
}

export const ideaRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'ideas/$symbol',
  validateSearch: validateIdeaSearch,
  ...idea,
  component: IdeaRoute,
});
