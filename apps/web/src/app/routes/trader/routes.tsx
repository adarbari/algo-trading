/**
 * TRADER workspace (the default): Ideas (home), Test, Edges, Explore, Regime, Calendar.
 * A pathless layout route, so its sections sit at the top level (`/ideas`, `/explore`, ...). The
 * Guide has its own group (routes/guide/).
 */
import { calendarRoute } from './calendar-route';
import { edgesRoute } from './edges-route';
import { exploreRoute } from './explore-route';
import { ideasRoute } from './ideas-route';
import { traderRoute } from './layout-route';
import { regimeRoute } from './regime-route';
import { legacyRoutes } from './redirects';
import { testRoutes } from './test-route';

export { traderRoute } from './layout-route';

export const traderRoutes = traderRoute.addChildren([
  ideasRoute,
  testRoutes,
  edgesRoute,
  ...legacyRoutes,
  exploreRoute,
  regimeRoute,
  calendarRoute,
]);
