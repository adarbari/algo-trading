/** Trader > Calendar: events ahead across names (no params). */
import { createRoute } from '@tanstack/react-router';

import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { lazyPage } from '@/shared/lib/lazy';

const CalendarPage = lazyPage(() => import('@/pages/trader-calendar'), 'CalendarPage');

export const calendarRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'calendar',
  ...pageRoute(
    CalendarPage,
    (page, client) => {
      page.prefetchCalendarReads(client);
    },
    true,
  ),
  component: CalendarPage,
});
