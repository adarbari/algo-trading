/** The router instance, registered for type-safe links and params everywhere. */
import { createRouter } from '@tanstack/react-router';

import { routeTree, type RouterContext } from '../routes';

// The query client arrives with `<RouterProvider context>` (App.tsx), so guards can read it.
export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  context: undefined as unknown as RouterContext,
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
