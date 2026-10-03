/** The root route: renders the matched workspace; `/` goes to the default workspace's home. */
import { createRootRoute, createRoute, Outlet, redirect } from '@tanstack/react-router';

import { DEFAULT_WORKSPACE } from '../workspaces';

export const rootRoute = createRootRoute({ component: Outlet });

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
    throw redirect({ to: DEFAULT_WORKSPACE.sections[0]?.path ?? '/ideas' });
  },
});
