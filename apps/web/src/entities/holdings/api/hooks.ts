/** Read hook for an ETF's holdings (by ticker or instrument id). */
import { useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

/** The `top` largest holdings. A non-ETF, or an ETF with nothing stored, answers empty. */
export function useEtfHoldings(key: string | null, top: number) {
  return useQuery({
    queryKey: queryKeys.holdings.etf(key ?? '', top),
    queryFn: () =>
      unwrap(
        api.GET('/instruments/{instrument_id}/holdings', {
          params: { path: { instrument_id: key ?? '' }, query: { top } },
        }),
      ),
    enabled: Boolean(key),
  });
}
