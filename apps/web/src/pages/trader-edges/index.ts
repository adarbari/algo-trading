import { prefetchEdges } from '@/entities/edge';
import { warmPage } from '@/shared/page-cache';

/** Page: Trader > Edges (the Edges Lab: the edges by verdict, and the chosen edge's page). */
export { EdgesPage, type EdgesPageProps } from './ui/EdgesPage';

// This chunk loads when the page's link is hovered: start its read then.
warmPage(prefetchEdges);
