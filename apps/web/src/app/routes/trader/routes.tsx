/**
 * TRADER workspace (the default): Ideas (home), Screeners, Explore, Backtests. A pathless
 * layout route, so its sections sit at the top level (`/ideas`, `/explore`, ...).
 */
import { TRADER } from '../../workspaces';
import { placeholderRoute } from '../section-route';

import { exploreRoute } from './explore-route';
import { traderRoute } from './layout-route';

export { traderRoute } from './layout-route';

export const traderRoutes = traderRoute.addChildren([
  placeholderRoute(traderRoute, TRADER, '/ideas', 'ideas'),
  placeholderRoute(traderRoute, TRADER, '/screeners', 'screeners'),
  exploreRoute,
  placeholderRoute(traderRoute, TRADER, '/backtests', 'backtests'),
]);
