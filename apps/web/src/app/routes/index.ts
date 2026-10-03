/** The route tree: root, then one route group per workspace (routes/<workspace>/). */
import { adminRoutes } from './admin/routes';
import { indexRoute, rootRoute } from './root';
import { traderRoutes } from './trader/routes';

export const routeTree = rootRoute.addChildren([indexRoute, traderRoutes, adminRoutes]);
