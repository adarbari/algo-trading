/**
 * The read hook for the declared people over GraphQL (`Query.userRegistry`, Admin only; ADR 0040,
 * ADR 0037): id, name, role and the data licences held, never an email. One operation serves the
 * Admin Users page.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const UserRegistryQuery = graphql(`
  query UserRegistry {
    userRegistry {
      people {
        id
        name
        role
        licences
        scheduled
      }
    }
  }
`);

/** Null: the Admin read returned nothing (no stores). */
export function useUserRegistry() {
  return useQuery({
    queryKey: queryKeys.gql('UserRegistry', {}),
    queryFn: ({ queryKey }) => gql(UserRegistryQuery, {}, queryKey),
    select: (data) => data.userRegistry,
  });
}
