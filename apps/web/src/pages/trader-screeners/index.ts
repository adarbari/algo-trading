/** Page: Trader > Screeners (the list of screeners with their results and track records). */
import { decodeFilters } from '@/features/filter-bar';
import { prefetchTrackRecords } from '@/entities/edge';
import {
  prefetchMyScreens,
  prefetchScreenerList,
  prefetchScreenerRuns,
  prefetchScreeners,
} from '@/entities/screen';
export { ScreenersPage, type ScreenersPageProps } from './ui/ScreenersPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchScreenersReads(
  client: Parameters<typeof prefetchScreeners>[0],
  f?: string,
  q = '',
): void {
  prefetchScreenerList(client, decodeFilters(f), q);
  prefetchScreeners(client);
  prefetchMyScreens(client);
  prefetchScreenerRuns(client);
  prefetchTrackRecords(client);
}
