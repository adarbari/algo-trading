/** Read hook for an underlying's option chain (one expiry, or every expiry when null). */
import { useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

export function useOptionChain(key: string | null, expiry: string | null) {
  return useQuery({
    queryKey: queryKeys.chains.chain(key ?? '', expiry),
    queryFn: () =>
      unwrap(
        api.GET('/chains/{underlying_id}', {
          params: { path: { underlying_id: key ?? '' }, query: { expiry: expiry ?? null } },
        }),
      ),
    enabled: Boolean(key),
    // Another expiry of the same underlying keeps the table on screen while it loads.
    placeholderData: (previous, query) => (query?.queryKey[1] === key ? previous : undefined),
  });
}
