/**
 * What a trader page's chunk does when it loads (a hovered link preloads it): start that page's
 * read and, once, the saved page cache. Nothing here is in the entry chunk: only a page, which
 * is loaded on demand, imports it.
 */
import type { QueryClient } from '@tanstack/react-query';

import { active } from '@/shared/api';

/** Run `prefetch` with the app's client; start the page cache (its own chunk) with it. */
export function warmPage(prefetch: (client: QueryClient) => void): void {
  const { client } = active;
  if (!client) return; // a test rendering a page alone: no app, nothing to warm
  prefetch(client);
  void import('./query-persistence').then((m) => m.startQueryPersistence(client));
}
