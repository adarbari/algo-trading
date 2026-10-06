/**
 * The root route: renders the matched route; `/` goes to the default workspace's home. The
 * router context carries the query client so route guards can read the viewer (guard.ts).
 */
import type { QueryClient } from '@tanstack/react-query';
import { createRootRouteWithContext, createRoute, Outlet, redirect } from '@tanstack/react-router';

import { DEFAULT_WORKSPACE } from '../workspaces';

export interface RouterContext {
  queryClient: QueryClient;
}

export const rootRoute = createRootRouteWithContext<RouterContext>()({ component: Outlet });

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
    throw redirect({ to: DEFAULT_WORKSPACE.sections[0]?.path ?? '/ideas' });
  },
});
