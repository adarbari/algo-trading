/**
 * Trader > an idea (`/ideas/$symbol?setup=`): the route validates the one search param (the setup
 * shown; absent: the best that picked the name) and opens the page. Back goes to Ideas on the
 * name's tab; a name opens in Explore with the setup's screener.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { lazyPage } from '@/shared/lib/lazy';

import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';

const IdeaPage = lazyPage(() => import('@/pages/trader-idea'), 'IdeaPage');

const loading = pageRoute(IdeaPage);

function validateSearch(raw: Record<string, unknown>): { setup?: string } {
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
  validateSearch,
  ...loading,
  component: IdeaRoute,
});
