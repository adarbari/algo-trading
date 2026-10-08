/** Trader > Calendar: events ahead across names (no params). */
import { createRoute, lazyRouteComponent } from '@tanstack/react-router';

import { traderRoute } from './layout-route';

const CalendarPage = lazyRouteComponent(() => import('@/pages/trader-calendar'), 'CalendarPage');

export const calendarRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'calendar',
  component: CalendarPage,
});
