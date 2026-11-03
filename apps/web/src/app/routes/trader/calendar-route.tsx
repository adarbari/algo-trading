/** Trader > Calendar: events ahead across names; the search param `f` is Earnings week's filter bar
 * (ADR 0082, surface `calendar_week`), so a filtered week is a shareable link. */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { filterSearch } from '@/features/filter-bar';

import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { lazyPage } from '@/shared/lib/lazy';

const CalendarPage = lazyPage(() => import('@/pages/trader-calendar'), 'CalendarPage');

function CalendarRoute() {
  const { f } = calendarRoute.useSearch();
  const navigate = useNavigate({ from: calendarRoute.fullPath });
  return (
    <CalendarPage
      f={f}
      onFilterChange={(next) => void navigate({ search: next ? { f: next } : {}, replace: true })}
    />
  );
}

export const calendarRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'calendar',
  validateSearch: filterSearch,
  ...pageRoute(CalendarPage, (page, client) => {
    page.prefetchCalendarReads(client);
  }),
  component: CalendarRoute,
});
