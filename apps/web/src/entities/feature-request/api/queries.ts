/**
 * The read hook for the ranked missing-feature requests over GraphQL (`Query.featureRequests`,
 * Admin only; ADR 0066, ADR 0037): one row per requested feature, best first, with counts and
 * never a user. One operation serves the whole page.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const FeatureRequestsQuery = graphql(`
  query FeatureRequests {
    featureRequests {
      today
      days
      rows {
        rank
        ref
        description
        feasibility
        score
        users
        timesAsked
        firstSeen
        lastSeen
        status
        promotedTo
        unmapped
      }
    }
  }
`);

/** Null: the Admin read returned nothing (no stores). */
export function useFeatureRequests() {
  return useQuery({
    queryKey: queryKeys.gql('FeatureRequests', {}),
    queryFn: () => gql(FeatureRequestsQuery, {}),
    select: (data) => data.featureRequests,
  });
}
