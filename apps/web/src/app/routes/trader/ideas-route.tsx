/**
 * Trader > Ideas: tickers open in Explore, one or as a compare set (Explore's search params); a
 * screener chip opens that screener's results.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { IdeasPage } from '@/pages/trader-ideas';

import { traderRoute } from './layout-route';

function IdeasRoute() {
  const navigate = useNavigate();
  return (
    <IdeasPage
      onCompare={(search) => void navigate({ to: '/explore', search })}
      onNewScreener={() => void navigate({ to: '/screeners/new' })}
      onScreeners={() => void navigate({ to: '/screeners' })}
      onOpenRegime={() => void navigate({ to: '/regime' })}
      onOpenScreener={(id) => void navigate({ to: '/screeners/$id', params: { id } })}
      onOpen={(symbol) => void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })}
    />
  );
}

export const ideasRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'ideas',
  component: IdeasRoute,
});
