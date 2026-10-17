/** Page: Trader > Edges (the Edges Lab: the edges by verdict, and the chosen edge's page). */
import { prefetchEdgeDesk, prefetchEdges } from '@/entities/edge';

export { EdgesPage, type EdgesPageProps } from './ui/EdgesPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchEdgesReads(client: Parameters<typeof prefetchEdges>[0]): void {
  prefetchEdges(client);
  prefetchEdgeDesk(client);
}
