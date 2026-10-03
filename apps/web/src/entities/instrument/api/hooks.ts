/**
 * Read hooks for one instrument (by ticker or id): its detail (reference, company, the
 * session's feature values), daily bars, events, and feature history.
 */
import { useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

export function useInstrument(key: string | null) {
  return useQuery({
    queryKey: queryKeys.instruments.detail(key ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/instruments/{instrument_id}', {
          params: { path: { instrument_id: key ?? '' } },
        }),
      ),
    enabled: Boolean(key),
  });
}

/** Split-adjusted daily bars from `from` (null: the API's default, the last year). */
export function useInstrumentBars(key: string | null, from: string | null) {
  return useQuery({
    queryKey: queryKeys.instruments.bars(key ?? '', from),
    queryFn: () =>
      unwrap(
        api.GET('/instruments/{instrument_id}/bars', {
          params: { path: { instrument_id: key ?? '' }, query: { from: from ?? null } },
        }),
      ),
    enabled: Boolean(key),
    // Another range of the same instrument keeps the chart on screen while it loads.
    placeholderData: (previous, query) => (query?.queryKey[1] === key ? previous : undefined),
  });
}

/** Every stored event (all time): dividends, splits, earnings, ticker and index changes. */
export function useInstrumentEvents(key: string | null) {
  return useQuery({
    queryKey: queryKeys.instruments.events(key ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/instruments/{instrument_id}/events', {
          params: { path: { instrument_id: key ?? '' } },
        }),
      ),
    enabled: Boolean(key),
  });
}

/** Every catalogue feature's values per session from `from` (the sparkline history). */
export function useFeatureHistory(key: string | null, from: string) {
  return useQuery({
    queryKey: queryKeys.instruments.features(key ?? '', from),
    queryFn: () =>
      unwrap(
        api.GET('/instruments/{instrument_id}/features', {
          params: { path: { instrument_id: key ?? '' }, query: { from } },
        }),
      ),
    enabled: Boolean(key),
  });
}
