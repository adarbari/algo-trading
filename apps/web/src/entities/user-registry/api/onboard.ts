/**
 * Onboard a trader (`POST /users`, Admin only; ID5): declares the user locally and returns the
 * one step left at the identity provider. The user list refetches so the new row, marked as
 * pending, shows at once.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

export interface OnboardInput {
  userId: string;
  email: string;
  name: string;
}

export function useOnboardUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, email, name }: OnboardInput) =>
      unwrap(api.POST('/users', { body: { user_id: userId, email, name } })),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.gql('UserRegistry', {}) }),
  });
}
