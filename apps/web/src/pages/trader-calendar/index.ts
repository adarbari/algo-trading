import { prefetchCalendar } from '@/entities/event';
import { prefetchScreeners } from '@/entities/screen';
import { warmPage } from '@/shared/page-cache';

/** Page: Trader > Calendar (the next 90 days of events across names). */
export { CalendarPage } from './ui/CalendarPage';

// This chunk loads when the page's link is hovered: start its reads then.
warmPage((client) => {
  prefetchCalendar(client);
  prefetchScreeners(client);
});
