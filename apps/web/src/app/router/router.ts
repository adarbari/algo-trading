/** The router instance, registered for type-safe links and params everywhere. */
import type { QueryClient } from '@tanstack/react-query';
import { createRouter } from '@tanstack/react-router';

import { routeTree, type RouterContext } from '../routes';
import { prefetchLayoutReadsEarly } from '../workspaces';

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

/**
 * Starts the opened page's reads now, beside the viewer's round trip, instead of after it: the
 * guard waits for the viewer before any loader, one round trip a distant client pays twice. Only
 * a route marked `early` (a trader page: the viewer's role cannot refuse it) runs; the loader
 * later joins the requests in flight.
 */
export function startEarlyReads(queryClient: QueryClient): void {
  const leaf = matched.at(-1);
  if (!leaf?.options.staticData?.early) return;
  prefetchLayoutReadsEarly(queryClient);
  try {
    const { search } = router.latestLocation;
    const validate = leaf.options.validateSearch as ((raw: unknown) => unknown) | undefined;
    const deps = (leaf.options.loaderDeps as ((a: { search: unknown }) => unknown) | undefined)?.({
      search: validate?.(search) ?? search,
    });
    const load = leaf.options.loader as (a: unknown) => Promise<void>;
    void load({ context: { queryClient }, deps }).catch(() => undefined);
  } catch {
    // a search the page cannot read: the router's own load shows its error, not a blank app
  }
}

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
