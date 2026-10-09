/** Page: Trader > Ideas (the ticker-level ideas table with its views and filters). */
import { active } from '@/shared/api';

export { IdeasPage, type IdeasPageProps } from './ui/IdeasPage';

// This chunk loads when the page's link is hovered: start the read, and the saved page cache.
const { client } = active;
if (client) {
  void import('@/entities/page-cache').then((m) => m.startQueryPersistence(client));
}
