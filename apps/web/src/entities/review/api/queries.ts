/** Read hooks for the owner's review lists: FIGI conflicts and leveraged ETFs to curate. */
import { useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

export function useFigiReview() {
  return useQuery({
    queryKey: queryKeys.admin.figiReview(),
    queryFn: () => unwrap(api.GET('/admin/review/figi')),
  });
}

export function useLeveragedReview() {
  return useQuery({
    queryKey: queryKeys.admin.leveragedReview(),
    queryFn: () => unwrap(api.GET('/admin/review/leveraged')),
  });
}
