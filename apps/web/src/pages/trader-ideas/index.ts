/** Page: Trader > Ideas (the ticker-level ideas table with its views and filters). */
import { prefetchIdeas } from '@/entities/idea';
import { warmPage } from '@/shared/page-cache';

export { IdeasPage, type IdeasPageProps } from './ui/IdeasPage';

// This chunk loads when the page's link is hovered: start its read then.
warmPage(prefetchIdeas);
