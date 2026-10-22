/**
 * The read hook for the formulas traders accepted in Describe it over GraphQL
 * (`Query.acceptedFormulas`, Admin only; ADR 0066, ADR 0037): one row per distinct formula (the
 * server groups by fingerprint), most users first, counts only and never a user.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const AcceptedFormulasQuery = graphql(`
  query AcceptedFormulas {
    acceptedFormulas {
      today
      days
      rows {
        fingerprint
        canonical
        expression
        unit
        description
        acceptedCount
        users
        firstAccepted
        lastAccepted
        duplicateOf
        backlogKey
      }
    }
  }
`);

/** Null: the Admin read returned nothing (no stores). */
export function useAcceptedFormulas() {
  return useQuery({
    queryKey: queryKeys.gql('AcceptedFormulas', {}),
    queryFn: ({ queryKey }) => gql(AcceptedFormulasQuery, {}, queryKey),
    select: (data) => data.acceptedFormulas,
  });
}
