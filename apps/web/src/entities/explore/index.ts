/** Entity: the Explore ticker table (universe x catalogue columns) and multi-ticker compare. */
export {
  fetchTickerTable,
  TICKER_PAGE_SIZE,
  useComparePrices,
  useCompareFeatures,
  useTickerTable,
  useUniverseSize,
} from './api/hooks';
export {
  priceSeries,
  rowValues,
  type FeatureComparison,
  type PriceComparison,
} from './model/compare';
export { isStale, STALE_AFTER_DAYS } from './model/freshness';
export {
  joinPages,
  tickerParams,
  toTickerRow,
  type TickerQuery,
  type TickerRow,
  type TickerTableData,
} from './model/ticker-table';
