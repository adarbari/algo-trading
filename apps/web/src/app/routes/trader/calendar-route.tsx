/** Trader > Calendar: events ahead across names (no params). */
import { createRoute } from '@tanstack/react-router';

import { traderRoute } from './layout-route';
import { lazyPage } from '@/shared/lib/lazy';

const CalendarPage = lazyPage(() => import('@/pages/trader-calendar'), 'CalendarPage');

export const calendarRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'calendar',
  component: CalendarPage,
});
