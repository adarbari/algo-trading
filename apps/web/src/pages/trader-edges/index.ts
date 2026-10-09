/** Page: Trader > Edges (the Edges Lab: the edges by verdict, and the chosen edge's page). */
import { prefetchEdges } from '@/entities/edge';
import { active } from '@/shared/api';

export { EdgesPage, type EdgesPageProps } from './ui/EdgesPage';

// This chunk loads when the page's link is hovered: start the read, and the saved page cache.
const { client } = active;
if (client) {
  prefetchEdges(client);
  void import('@/entities/page-cache').then((m) => m.startQueryPersistence(client));
}
