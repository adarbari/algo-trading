import { prefetchRegime } from '@/entities/regime';
import { warmPage } from '@/shared/page-cache';

/** Page: Trader > Regime (the market as weather, its warning signs, the reading list). */
export { RegimePage } from './ui/RegimePage';

// This chunk loads when the page's link is hovered: start its read then.
warmPage(prefetchRegime);
