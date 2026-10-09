/** Page: Trader > Regime (the market as weather, its warning signs, the reading list). */
import { active } from '@/shared/api';

export { RegimePage } from './ui/RegimePage';

// This chunk loads when the page's link is hovered: start the read, and the saved page cache.
const { client } = active;
if (client) {
  void import('@/entities/page-cache').then((m) => m.startQueryPersistence(client));
}
