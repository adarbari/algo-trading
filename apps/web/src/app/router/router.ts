/** The router instance, registered for type-safe links and params everywhere. */
import { createRouter } from '@tanstack/react-router';

import { routeTree, type RouterContext } from '../routes';

// The query client arrives with `<RouterProvider context>` (App.tsx), so guards can read it.
export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  context: undefined as unknown as RouterContext,
});

// The page chunk of the URL's route downloads now, beside the viewer's round trip (the route
// guard waits for the viewer before any loader runs).
const [matched] = router.getMatchedRoutes(router.latestLocation.pathname);
for (const route of matched) void route.options.staticData?.preload?.().catch(() => undefined);

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
