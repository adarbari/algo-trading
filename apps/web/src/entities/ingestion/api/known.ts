/**
 * Read hook for the fundamentals share count known against the rows stored over GraphQL
 * (`Query.knownCoverage`; ADR 0037): admin only, for exactly the served session, `unknown`
 * NOT_RUN when no nightly record of it holds the breakdown.
 */
import { queryOptions, useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const KnownCoverage = graphql(`
  query KnownCoverage {
    knownCoverage {
      session
      runId
      byType {
        securityType
        names
        rows
        known
        share
      }
      gaps {
        gap
        names
      }
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

function knownCoverageQuery() {
  return queryOptions({
    queryKey: queryKeys.gql('KnownCoverage', {}),
    queryFn: ({ queryKey }) => gql(KnownCoverage, {}, queryKey),
  });
}

/** Null: nothing stored. */
export function useKnownCoverage() {
  return useQuery({ ...knownCoverageQuery(), select: (data) => data.knownCoverage });
}
