/**
 * Read hooks for the owner's review lists over GraphQL (`Query.{figiReview,leverageReview}`;
 * ADR 0037): FIGI conflicts and leveraged ETFs to curate, for the latest session's snapshot.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const FigiReview = graphql(`
  query FigiReview {
    figiReview {
      session
      source
      items
    }
  }
`);

const LeverageReview = graphql(`
  query LeverageReview {
    leverageReview {
      session
      source
      items
    }
  }
`);

/** Null: nothing stored. */
export function useFigiReview() {
  return useQuery({
    queryKey: queryKeys.gql('FigiReview', {}),
    queryFn: () => gql(FigiReview, {}),
    select: (data) => data.figiReview,
  });
}

/** Null: nothing stored. */
export function useLeveragedReview() {
  return useQuery({
    queryKey: queryKeys.gql('LeverageReview', {}),
    queryFn: () => gql(LeverageReview, {}),
    select: (data) => data.leverageReview,
  });
}
