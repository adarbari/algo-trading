/** Page: Trader > Edges (the Edges Lab: the edges by verdict, and the chosen edge's page). */
import { decodeFilters } from '@/features/filter-bar';
import { prefetchEdge, prefetchEdgeDesk, prefetchEdges } from '@/entities/edge';

export { EdgesPage, type EdgesPageProps } from './ui/EdgesPage';

/**
 * Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. An
 * edge named by the URL reads that one edge, not the list (the page shows only the edge).
 */
export function prefetchEdgesReads(
  client: Parameters<typeof prefetchEdges>[0],
  edge?: string | null,
  f?: string,
  q = '',
): void {
  if (edge) prefetchEdge(client, edge);
  else prefetchEdges(client, decodeFilters(f), q);
  prefetchEdgeDesk(client);
}
