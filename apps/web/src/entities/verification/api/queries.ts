/**
 * Read hook for the latest session's live verification vs IBKR over GraphQL
 * (`Query.verification`; ADR 0037): for exactly that session, `unknown` NO_PARTITION when the
 * verify step did not run for it.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { toVerification } from '../model/summary';

const Verification = graphql(`
  query Verification {
    verification {
      session
      runIds
      instruments
      counts
      byCheck {
        check
        counts
      }
      failing
      unknown {
        code
        detail
      }
    }
  }
`);

/** Null: nothing stored. */
export function useVerification() {
  return useQuery({
    queryKey: queryKeys.gql('Verification', {}),
    queryFn: () => gql(Verification, {}),
    select: (data) => (data.verification ? toVerification(data.verification) : null),
  });
}
