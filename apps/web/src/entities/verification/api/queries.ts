/**
 * Read hook for the latest session's live verification vs IBKR over GraphQL
 * (`Query.verification`; ADR 0037): for exactly that session, `unknown` NO_PARTITION when the
 * verify step did not run for it.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

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
        kind
        guideTerm
        kindText
        cause {
          links {
            level
            subject
            status
            message
            runId
          }
        }
      }
    }
  }
`);

function verificationQuery() {
  return queryOptions({
    queryKey: queryKeys.gql('Verification', {}),
    queryFn: () => gql(Verification, {}),
  });
}

/** Start the read before the page mounts (a route loader); the hook then joins it. */
export function prefetchVerification(client: QueryClient): void {
  void client.query(verificationQuery()).catch(() => undefined);
}

/** Null: nothing stored. */
export function useVerification() {
  return useQuery({
    ...verificationQuery(),
    select: (data) => (data.verification ? toVerification(data.verification) : null),
  });
}
