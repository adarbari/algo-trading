/**
 * TRADER workspace (the default): Ideas (home), Screeners, Explore, Backtests. A pathless
 * layout route, so its sections sit at the top level (`/ideas`, `/explore`, ...).
 */
import { TRADER } from '../../workspaces';
import { placeholderRoute } from '../section-route';

import { exploreRoute } from './explore-route';
import { ideasRoute } from './ideas-route';
import { traderRoute } from './layout-route';
import { screenersRoutes } from './screeners-route';

export { traderRoute } from './layout-route';

export const traderRoutes = traderRoute.addChildren([
  ideasRoute,
  screenersRoutes,
  exploreRoute,
  placeholderRoute(traderRoute, TRADER, '/backtests', 'backtests'),
]);
