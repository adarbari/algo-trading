/** Page: Trader > Ideas (the ticker-level ideas table with its views and filters). */
import { prefetchEdgeDesk } from '@/entities/edge';
import { prefetchIdeas } from '@/entities/idea';
import { prefetchRegime } from '@/entities/regime';

export { IdeasPage, preloadEdgeSignals, type IdeasPageProps } from './ui/IdeasPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchIdeasReads(client: Parameters<typeof prefetchIdeas>[0]): void {
  prefetchRegime(client);
  prefetchIdeas(client);
  prefetchEdgeDesk(client);
}
