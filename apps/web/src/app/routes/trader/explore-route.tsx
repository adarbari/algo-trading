/**
 * Trader > Explore: the route validates the search params (Explore's whole state, so views
 * are shareable links) and hands them to the page with a setter that replaces the URL.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { parseExploreSearch, type ExploreSearch } from '@/entities/explore';
import type { SearchPatch } from '@/pages/trader-explore';

import { traderRoute } from './layout-route';
import { lazyPage } from '@/shared/lib/lazy';

const ExplorePage = lazyPage(() => import('@/pages/trader-explore'), 'ExplorePage');

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
  component: ExploreRoute,
});
