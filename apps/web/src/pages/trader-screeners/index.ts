/** Page: Trader > Screeners (the list of screeners with their results and track records). */
import { prefetchScreeners } from '@/entities/screen';
import { warmPage } from '@/shared/page-cache';

export { ScreenersPage, type ScreenersPageProps } from './ui/ScreenersPage';

// This chunk loads when the page's link is hovered: start its read then.
warmPage(prefetchScreeners);
