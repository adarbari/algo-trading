/** Trader > Regime: the market as weather (no params; the page reads the session's regime). */
import { createRoute, lazyRouteComponent } from '@tanstack/react-router';

import { traderRoute } from './layout-route';

const RegimePage = lazyRouteComponent(() => import('@/pages/trader-regime'), 'RegimePage');

export const regimeRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'regime',
  component: RegimePage,
});
