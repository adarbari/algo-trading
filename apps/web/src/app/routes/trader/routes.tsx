/**
 * TRADER workspace (the default): Ideas (home), Screeners, Explore, Regime, Calendar, Backtests,
 * and the Guide (a utility link, not a section). A pathless layout route, so its sections sit at
 * the top level (`/ideas`, `/explore`, `/guide`, ...).
 */
import { TRADER } from '../../workspaces';
import { placeholderRoute } from '../section-route';

import { calendarRoute } from './calendar-route';
import { exploreRoute } from './explore-route';
import { guideRoutes } from './guide-route';
import { ideasRoute } from './ideas-route';
import { traderRoute } from './layout-route';
import { regimeRoute } from './regime-route';
import { screenersRoutes } from './screeners-route';

export { traderRoute } from './layout-route';

export const traderRoutes = traderRoute.addChildren([
  ideasRoute,
  screenersRoutes,
  exploreRoute,
  regimeRoute,
  calendarRoute,
  guideRoutes,
  placeholderRoute(traderRoute, TRADER, '/backtests', 'backtests'),
]);
