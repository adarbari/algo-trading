/**
 * The opened trader page's reads at start-up, beside the viewer's round trip. The workspace guard
 * waits for the viewer before any loader, which costs a distant client one more round trip before
 * the page's data leaves. This module (a lazy chunk the build preloads from index.html, so the
 * entry stays small) runs the matched page route's own loader at once with the URL's search; the
 * loader later joins the requests in flight. Only trader pages: any registered viewer may open
 * them, so the viewer's role cannot refuse a read started early. Admin pages wait for the guard.
 */
import type { QueryClient } from '@tanstack/react-query';

import { active } from '@/shared/api';

import { router } from './router';

/** The trader pages whose loader may run before the guard. */
export const EARLY_PATHS = ['/ideas', '/screeners', '/edges', '/regime', '/calendar', '/explore'];

export function startEarlyReads(queryClient: QueryClient): void {
  const [matched] = router.getMatchedRoutes(router.latestLocation.pathname);
  const leaf = matched.at(-1);
  const path = (leaf?.fullPath as string | undefined)?.replace(/\/$/, '');
  if (!leaf || path === undefined || !EARLY_PATHS.includes(path)) return;
  try {
    const { search } = router.latestLocation;
    const validate = leaf.options.validateSearch as ((raw: unknown) => unknown) | undefined;
    const loaderDeps = leaf.options.loaderDeps as ((a: { search: unknown }) => unknown) | undefined;
    const deps = loaderDeps?.({ search: validate?.(search) ?? search });
    const load = leaf.options.loader as (a: unknown) => Promise<void>;
    void load({ context: { queryClient }, deps }).catch(() => undefined);
  } catch {
    // a search the page cannot read: the router's own load shows its error
  }
}

// Importing the module starts the reads for the app's own client (`createQueryClient` sets it).
if (active.client) startEarlyReads(active.client);
