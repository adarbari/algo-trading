/**
 * The route tree: root, the login page, one route group per workspace (routes/<workspace>/) and
 * the Guide's own group (routes/guide/), which belongs to no workspace.
 */
import { adminRoutes } from './admin/routes';
import { guideRoutes } from './guide/routes';
import { loginRoute } from './login-route';
import { indexRoute, rootRoute } from './root';
import { traderRoutes } from './trader/routes';

export type { RouterContext } from './root';

export const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  traderRoutes,
  adminRoutes,
  guideRoutes,
]);
