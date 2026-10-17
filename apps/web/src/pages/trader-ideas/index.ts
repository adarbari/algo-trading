/** Page: Trader > Ideas (the ticker-level ideas table with its views and filters). */
import { prefetchEdgeDesk } from '@/entities/edge';
import { prefetchIdeas } from '@/entities/idea';
import { prefetchRegime } from '@/entities/regime';
import { active } from '@/shared/api';

export { IdeasPage, preloadEdgeSignals, type IdeasPageProps } from './ui/IdeasPage';

// This chunk loads when the page's link is hovered: start the read, and the saved page cache.
const { client } = active;
if (client) {
  void import('@/entities/page-cache').then((m) => m.startQueryPersistence(client));
}

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchIdeasReads(client: Parameters<typeof prefetchIdeas>[0]): void {
  prefetchRegime(client);
  prefetchIdeas(client);
  prefetchEdgeDesk(client);
}
