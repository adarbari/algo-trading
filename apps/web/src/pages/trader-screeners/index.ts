/** Page: Trader > Screeners (the list of screeners with their results and track records). */
import { prefetchScreeners } from '@/entities/screen';
import { active } from '@/shared/api';

export { ScreenersPage, type ScreenersPageProps } from './ui/ScreenersPage';

// This chunk loads when the page's link is hovered: start the read, and the saved page cache.
const { client } = active;
if (client) {
  prefetchScreeners(client);
  void import('@/entities/page-cache').then((m) => m.startQueryPersistence(client));
}
