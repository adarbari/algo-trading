/**
 * The loader every page route shares (ADR 0037's performance rules, owner goal 2026-10-17: data
 * on screen in under 100 ms on a reload and 500 ms on a first visit): it loads the page's chunk
 * (so the page renders unsuspended, see `lazyPage`), starts the page's reads with the page's own
 * exported `prefetch…Reads` (the hooks join the requests in flight and stay the one source of
 * query keys), and gives the saved page cache a moment to land so a returning visit renders from
 * it. It never waits for data. The page chunk is imported dynamically: the entry carries none
 * of the pages' entities (perf-budgets.json).
 */
import type { QueryClient } from '@tanstack/react-query';

import type { RouterContext } from './root';

/** How long the loader waits for the saved page cache to be read, at most. */
export const RESTORE_WAIT_MS = 150;

export interface PageModule<M> {
  load: () => Promise<M>;
  preload: () => Promise<void>;
}

declare module '@tanstack/react-router' {
  interface StaticDataRouteOption {
    /** Fetches the route's page chunk; the router calls it for the URL's routes at start-up. */
    preload?: () => Promise<void>;
  }
}

type Prefetch<M> = (module: M, client: QueryClient) => void | Promise<void>;

/** Waits for the saved page cache to be read into the client (never longer than the cap). */
const restored = (client: QueryClient) =>
  import('@/entities/page-cache').then((m) => m.whenRestored(client, RESTORE_WAIT_MS));

/**
 * A page route's options: the `loader` (chunk, then the page's reads, then the saved page cache)
 * and the static `preload`, so the chunk starts downloading at start-up beside the viewer's
 * round trip instead of after it (the guard runs before any loader).
 */
export function pageRoute<M>(page: PageModule<M>, prefetch?: Prefetch<M>) {
  return {
    staticData: { preload: page.preload },
    // `context` is untyped here: the admin routes are built over any parent route.
    loader: async ({ context }: { context: unknown }): Promise<void> => {
      const { queryClient } = context as RouterContext;
      const module = await page.load();
      const started = prefetch?.(module, queryClient);
      await Promise.all([started, restored(queryClient)]);
    },
  };
}
