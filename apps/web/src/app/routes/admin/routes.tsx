/** ADMIN workspace under `/admin`: Ingestion, Screener runs & sharing, Users & configs. */
import { createRoute } from '@tanstack/react-router';

import { WorkspaceLayout } from '../../layouts';
import { ADMIN, workspaceGuard } from '../../workspaces';
import { rootRoute } from '../root';
import { placeholderRoute } from '../section-route';
import { ingestionRoute } from './ingestion';

export const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: 'admin',
  beforeLoad: workspaceGuard('admin'),
  component: () => <WorkspaceLayout workspace={ADMIN} />,
});

export const adminRoutes = adminRoute.addChildren([
  ingestionRoute(adminRoute),
  placeholderRoute(adminRoute, ADMIN, '/admin/screener-runs', 'screener-runs'),
  placeholderRoute(adminRoute, ADMIN, '/admin/users', 'users'),
]);
