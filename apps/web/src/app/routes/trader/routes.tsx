/**
 * TRADER workspace (the default): Ideas (home), Screeners, Explore, Backtests. A pathless
 * layout route, so its sections sit at the top level (`/ideas`, `/explore`, ...).
 */
import { createRoute } from '@tanstack/react-router';

import { WorkspaceLayout } from '../../layouts';
import { TRADER, workspaceGuard } from '../../workspaces';
import { rootRoute } from '../root';
import { placeholderRoute } from '../section-route';

export const traderRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'trader',
  beforeLoad: workspaceGuard('trader'),
  component: () => <WorkspaceLayout workspace={TRADER} />,
});

export const traderRoutes = traderRoute.addChildren([
  placeholderRoute(traderRoute, TRADER, '/ideas', 'ideas'),
  placeholderRoute(traderRoute, TRADER, '/screeners', 'screeners'),
  placeholderRoute(traderRoute, TRADER, '/explore', 'explore'),
  placeholderRoute(traderRoute, TRADER, '/backtests', 'backtests'),
]);
