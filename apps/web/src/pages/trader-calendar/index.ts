/** Page: Trader > Calendar (the next 90 days of events across names). */
import { prefetchCalendar } from '@/entities/event';
import { prefetchScreeners } from '@/entities/screen';
import { active } from '@/shared/api';

export { CalendarPage } from './ui/CalendarPage';

// This chunk loads when the page's link is hovered: start the read, and the saved page cache.
const { client } = active;
if (client) {
  prefetchCalendar(client);
  prefetchScreeners(client);
  void import('@/entities/page-cache').then((m) => m.startQueryPersistence(client));
}
