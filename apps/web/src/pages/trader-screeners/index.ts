/** Page: Trader > Screeners (the list of screeners with their results and track records). */
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
  filters: Parameters<typeof prefetchScreenerList>[1] = [],
  q = '',
): void {
  prefetchScreenerList(client, filters, q);
  prefetchScreeners(client);
  prefetchMyScreens(client);
  prefetchScreenerRuns(client);
  prefetchTrackRecords(client);
}
