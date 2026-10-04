/** Read hook for the latest live verification vs IBKR. */
import { useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

export function useVerification() {
  return useQuery({
    queryKey: queryKeys.admin.verification(),
    queryFn: () => unwrap(api.GET('/admin/verification/ibkr')),
  });
}
