/**
 * Read hooks for Explore: the whole ticker table for a query (every page, fetched in
 * parallel after the first), the universe size, and multi-ticker compare (features, prices).
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

import {
  joinPages,
  tickerParams,
  type TickerQuery,
  type TickerTableData,
} from '../model/ticker-table';

/** The API's largest page: about 12 requests for the full 11k-ticker universe. */
export const TICKER_PAGE_SIZE = 1000;

async function fetchTickerPage(query: TickerQuery, page: number) {
  return unwrap(
    api.GET('/explore/tickers', { params: { query: tickerParams(query, page, TICKER_PAGE_SIZE) } }),
  );
}

export async function fetchTickerTable(query: TickerQuery): Promise<TickerTableData> {
  const first = await fetchTickerPage(query, 1);
  const pages = Math.ceil(first.page.total / TICKER_PAGE_SIZE);
  const rest = await Promise.all(
    Array.from({ length: Math.max(0, pages - 1) }, (_, i) => fetchTickerPage(query, i + 2)),
  );
  return joinPages([first, ...rest]);
}

/** Every ticker matching the query; the previous table stays on screen while a new one loads. */
export function useTickerTable(query: TickerQuery) {
  return useQuery({
    queryKey: queryKeys.explore.tickers({ ...query }),
    queryFn: () => fetchTickerTable(query),
    placeholderData: keepPreviousData,
  });
}

/** How many tickers the universe holds (no filters): the table's "of N". */
export function useUniverseSize() {
  return useQuery({
    queryKey: queryKeys.explore.tickers({ size: 1 }),
    queryFn: () => unwrap(api.GET('/explore/tickers', { params: { query: { size: 1 } } })),
    select: (table) => table.page.total,
  });
}

/** Feature values side by side (one row per feature, one value per ticker). */
export function useCompareFeatures(symbols: readonly string[], features: readonly string[]) {
  return useQuery({
    queryKey: queryKeys.explore.compare(symbols, features),
    queryFn: () =>
      unwrap(
        api.GET('/explore/compare', {
          params: { query: { ids: symbols.join(','), features: features.join(',') } },
        }),
      ),
    enabled: symbols.length > 0 && features.length > 0,
    placeholderData: keepPreviousData,
  });
}

/** Closes on one date axis from `from` (null: all stored history), rebased to 100. */
export function useComparePrices(symbols: readonly string[], from: string | null) {
  return useQuery({
    queryKey: queryKeys.explore.prices(symbols, from),
    queryFn: () =>
      unwrap(
        api.GET('/explore/compare/prices', {
          params: {
            query: { ids: symbols.join(','), from: from ?? null, rebase: 100 },
          },
        }),
      ),
    enabled: symbols.length > 0,
    placeholderData: keepPreviousData,
  });
}
