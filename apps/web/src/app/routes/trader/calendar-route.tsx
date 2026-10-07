/** Trader > Calendar: events ahead across names (no params). */
import { createRoute } from '@tanstack/react-router';

import { CalendarPage } from '@/pages/trader-calendar';

import { traderRoute } from './layout-route';

export const calendarRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'calendar',
  component: CalendarPage,
});
