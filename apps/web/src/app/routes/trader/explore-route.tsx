/**
 * Trader > Explore: the route validates the search params (Explore's whole state, so views
 * are shareable links) and hands them to the page with a setter that replaces the URL.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { filterSearch, type FilterSearch } from '@/features/filter-bar';
import { parseExploreSearch, type ExploreSearch } from '@/entities/explore';
import type { SearchPatch } from '@/pages/trader-explore';

import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { lazyPage } from '@/shared/lib/lazy';

const ExplorePage = lazyPage(() => import('@/pages/trader-explore'), 'ExplorePage');

/** The search params after a patch: `undefined` removes a key. */
function patched(
  previous: ExploreSearch & FilterSearch,
  patch: SearchPatch,
): ExploreSearch & FilterSearch {
  const merged: Record<string, unknown> = { ...previous, ...patch };
  return validateSearch(
    Object.fromEntries(Object.entries(merged).filter(([, value]) => value !== undefined)),
  );
}

/** Explore's own params and the filter bar's `f` (the universe table's filters). */
function validateSearch(raw: Record<string, unknown>): ExploreSearch & FilterSearch {
  return { ...parseExploreSearch(raw), ...filterSearch(raw) };
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
  validateSearch,
  // the tab the URL opens on loads its chunk and starts its reads here, not when it mounts
  loaderDeps: ({ search }) => search,
  ...pageRoute(ExplorePage, (page, client, search: ExploreSearch) =>
    page.prefetchExploreReads(client, search),
  ),
  component: ExploreRoute,
});
