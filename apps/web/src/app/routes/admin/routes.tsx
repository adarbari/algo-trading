/** ADMIN workspace under `/admin`: Ingestion, LLM usage & cost, Edge runs, Feature requests, Screener runs & sharing, Users & configs. */
import { createRoute } from '@tanstack/react-router';

import { WorkspaceLayout } from '../../layouts';
import { ADMIN, workspaceGuard } from '../../workspaces';
import { rootRoute } from '../root';
import { placeholderRoute } from '../section-route';
import { featureRequestsRoute } from './feature-requests';
import { harnessRunsRoute } from './harness-runs';
import { ingestionRoute } from './ingestion';
import { llmUsageRoute } from './llm-usage';

export const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: 'admin',
  beforeLoad: workspaceGuard('admin'),
  component: () => <WorkspaceLayout workspace={ADMIN} />,
});

export const adminRoutes = adminRoute.addChildren([
  ingestionRoute(adminRoute),
  llmUsageRoute(adminRoute),
  harnessRunsRoute(adminRoute),
  featureRequestsRoute(adminRoute),
  placeholderRoute(adminRoute, ADMIN, '/admin/screener-runs', 'screener-runs'),
  placeholderRoute(adminRoute, ADMIN, '/admin/users', 'users'),
]);
