/** The route tree: root, the login page, then one route group per workspace (routes/<workspace>/). */
import { adminRoutes } from './admin/routes';
import { loginRoute } from './login-route';
import { indexRoute, rootRoute } from './root';
import { traderRoutes } from './trader/routes';

export type { RouterContext } from './root';

export const routeTree = rootRoute.addChildren([indexRoute, loginRoute, traderRoutes, adminRoutes]);
