/** Page: Trader > Screeners (the list of screeners with their results and track records). */
import { prefetchTrackRecords } from '@/entities/edge';
import { prefetchMyScreens, prefetchScreenerRuns, prefetchScreeners } from '@/entities/screen';
export { ScreenersPage, type ScreenersPageProps } from './ui/ScreenersPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchScreenersReads(client: Parameters<typeof prefetchScreeners>[0]): void {
  prefetchScreeners(client);
  prefetchMyScreens(client);
  prefetchScreenerRuns(client);
  prefetchTrackRecords(client);
}
