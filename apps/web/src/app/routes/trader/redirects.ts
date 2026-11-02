/**
 * The old Screeners and edge-builder URLs, redirected into the Test flow (`test-route.tsx`) with
 * their search (the filter bar's `f`, the search text `q`, a builder's `returnTo`), so a saved link
 * or an old bookmark still opens the same screen. The list and a screener's results are
 * `/screeners` and `/screeners/$id`; the Builder `/screeners/$id/edit` and `/screeners/new`; the
 * edge builder `/edges/new` and `/edges/$id/edit`.
 */
import { createRoute, redirect, type RegisteredRouter } from '@tanstack/react-router';

import { filterSearch } from '@/features/filter-bar';
import { traderRoute } from './layout-route';
import { validateTestSearch } from './test-route';

/** Redirect (replacing the history entry) to `options`. */
function bounce(options: Parameters<typeof redirect<RegisteredRouter>>[0]): never {
  // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
  throw redirect({ ...options });
}

/** The search a redirect carries on (builders' `returnTo`; the rest the target validates). */
const carried = (search: Record<string, unknown>) => search as Record<string, string>;

export const legacyRoutes = [
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'screeners',
    validateSearch: validateTestSearch,
    beforeLoad: ({ search }) => {
      bounce({ to: '/test', search });
    },
  }),
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'screeners/new',
    beforeLoad: ({ search }) => {
      bounce({ to: '/test/expert', search: carried(search) });
    },
  }),
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'screeners/$id',
    validateSearch: filterSearch,
    beforeLoad: ({ params, search }) => {
      bounce({ to: '/test/result/$id', params, search });
    },
  }),
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'screeners/$id/edit',
    beforeLoad: ({ params, search }) => {
      bounce({
        to: '/test/expert/$id',
        params,
        search: carried(search),
      });
    },
  }),
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'edges/new',
    beforeLoad: () => {
      bounce({ to: '/test/setup' });
    },
  }),
  createRoute({
    getParentRoute: () => traderRoute,
    path: 'edges/$id/edit',
    beforeLoad: ({ params }) => {
      bounce({ to: '/test/setup/$id', params });
    },
  }),
];
