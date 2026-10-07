/**
 * Trader > Explore: the route validates the search params (Explore's whole state, so views
 * are shareable links) and hands them to the page with a setter that replaces the URL. The
 * retired Field guide tab (`tab=guide`) redirects to the Guide for one release: to the field's
 * page when the link named one, else to the field index (narrowed to the theme it named).
 */
import { createRoute, redirect, useNavigate } from '@tanstack/react-router';

import { fieldPath, GUIDE_FIELDS_PATH } from '@/entities/guide';
import {
  ExplorePage,
  parseExploreSearch,
  type ExploreSearch,
  type SearchPatch,
} from '@/pages/trader-explore';

import { traderRoute } from './layout-route';

/** The search params after a patch: `undefined` removes a key. */
function patched(previous: ExploreSearch, patch: SearchPatch): ExploreSearch {
  const merged: Record<string, unknown> = { ...previous, ...patch };
  return parseExploreSearch(
    Object.fromEntries(Object.entries(merged).filter(([, value]) => value !== undefined)),
  );
}

function ExploreRoute() {
  const search = exploreRoute.useSearch();
  const navigate = useNavigate({ from: exploreRoute.fullPath });
  const onSearchChange = (patch: SearchPatch) =>
    void navigate({ search: (previous) => patched(previous, patch), replace: true });
  return (
    <ExplorePage
      search={search}
      onSearchChange={onSearchChange}
      onOpenScreener={(id) => void navigate({ to: '/screeners/$id', params: { id } })}
    />
  );
}

export const exploreRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'explore',
  validateSearch: parseExploreSearch,
  beforeLoad: ({ search }) => {
    if (search.tab !== 'guide') return;
    // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
    throw redirect(
      search.field
        ? { to: fieldPath(search.field) }
        : { to: GUIDE_FIELDS_PATH, search: search.theme ? { theme: search.theme } : {} },
    );
  },
  component: ExploreRoute,
});
