/** Trader > Regime: the market as weather (no params; the page reads the session's regime). */
import { createRoute } from '@tanstack/react-router';

import { traderRoute } from './layout-route';
import { lazyPage } from '../lazy-page';

const RegimePage = lazyPage(() => import('@/pages/trader-regime'), 'RegimePage');

export const regimeRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'regime',
  component: RegimePage,
});
