/**
 * Entity: Explore's compare chart (the compare set's closes, rebased for display) and how
 * fresh a session is. The ticker table and the side-by-side values are the feature table
 * (`@/entities/feature`).
 */
export { useComparePrices } from './api/hooks';
export { priceSeries, REBASE, toCompared, type ComparedPrices } from './model/compare';
export { isStale, STALE_AFTER_DAYS } from './model/freshness';
