/**
 * The TRADER workspace's layout route (the default workspace): pathless, so its sections sit
 * at the top level (`/ideas`, `/explore`, ...), behind the workspace guard.
 */
import { createRoute } from '@tanstack/react-router';

import { WorkspaceLayout } from '../../layouts';
import { TRADER, workspaceGuard } from '../../workspaces';
import { rootRoute } from '../root';

export const traderRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'trader',
  beforeLoad: workspaceGuard('trader'),
  component: () => <WorkspaceLayout workspace={TRADER} />,
});
