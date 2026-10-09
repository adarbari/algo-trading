/**
 * Entity: Explore's URL state (the open tickers and what each tab shows), the compare chart (the
 * open tickers' closes, rebased for display) and how fresh a session is. The side-by-side values
 * are the feature table (`@/entities/feature`).
 */
export { useComparePrices } from './api/hooks';
export { priceSeries, REBASE, toCompared, type ComparedPrices } from './model/compare';
export { isStale, STALE_AFTER_DAYS } from './model/freshness';
export {
  DEFAULT_DIMENSIONS,
  EXPLORE_TABS,
  joinList,
  parseExploreSearch,
  splitList,
  type ExploreSearch,
  type ExploreTab,
} from './model/search';
