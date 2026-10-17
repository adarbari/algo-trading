/** Page: Trader > Calendar (the next 90 days of events across names). */
import { prefetchCalendar } from '@/entities/event';
import { prefetchScreeners } from '@/entities/screen';

export { CalendarPage } from './ui/CalendarPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchCalendarReads(client: Parameters<typeof prefetchCalendar>[0]): void {
  prefetchCalendar(client);
  prefetchScreeners(client);
}
