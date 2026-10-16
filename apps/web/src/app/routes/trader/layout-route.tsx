/**
 * The TRADER workspace's layout route (the default workspace): pathless, so its sections sit
 * at the top level (`/ideas`, `/explore`, ...), behind the workspace guard.
 */
import { createRoute } from '@tanstack/react-router';

import { prefetchStatusStrip } from '@/entities/system-status';
import { ensureViewer } from '@/entities/viewer';

import { WorkspaceLayout } from '../../layouts';
import { canEnter, TRADER, workspaceGuard } from '../../workspaces';
import { rootRoute } from '../root';

export const traderRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'trader',
  beforeLoad: workspaceGuard('trader'),
  // The strip's read starts with the route, not when the layout mounts.
  loader: async ({ context }) => {
    const viewer = await ensureViewer(context.queryClient);
    if (viewer) prefetchStatusStrip(context.queryClient, canEnter(viewer, 'admin'));
  },
  component: () => <WorkspaceLayout workspace={TRADER} />,
});
