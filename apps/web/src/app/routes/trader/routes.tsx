/**
 * TRADER workspace (the default): Ideas (home), Screeners, Edges, Explore, Regime, Calendar, Backtests,
 * A pathless layout route, so its sections sit at the top level (`/ideas`, `/explore`, ...). The
 * Guide has its own group (routes/guide/).
 */
import { TRADER } from '../../workspaces';
import { placeholderRoute } from '../section-route';

import { calendarRoute } from './calendar-route';
import { edgesBuilderRoutes, edgesRoute } from './edges-route';
import { exploreRoute } from './explore-route';
import { ideasRoute } from './ideas-route';
import { traderRoute } from './layout-route';
import { regimeRoute } from './regime-route';
import { screenersRoutes } from './screeners-route';

export { traderRoute } from './layout-route';

export const traderRoutes = traderRoute.addChildren([
  ideasRoute,
  screenersRoutes,
  edgesRoute,
  ...edgesBuilderRoutes,
  exploreRoute,
  regimeRoute,
  calendarRoute,
  placeholderRoute(traderRoute, TRADER, '/backtests', 'backtests'),
]);
