/** Trader > Ideas: tickers open in Explore, one or as a compare set (Explore's search params). */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { IdeasPage } from '@/pages/trader-ideas';

import { traderRoute } from './layout-route';

function IdeasRoute() {
  const navigate = useNavigate();
  return (
    <IdeasPage
      onCompare={(search) => void navigate({ to: '/explore', search })}
      onNewScreener={() => void navigate({ to: '/screeners/new' })}
      onOpen={(symbol) => void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })}
    />
  );
}

export const ideasRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'ideas',
  component: IdeasRoute,
});
