/**
 * Read hooks for the owner's review lists over GraphQL (`Query.{figiReview,leverageReview}`;
 * ADR 0037): FIGI conflicts and leveraged ETFs to curate, for the latest session's snapshot.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

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

function figiReviewQuery() {
  return queryOptions({
    queryKey: queryKeys.gql('FigiReview', {}),
    queryFn: () => gql(FigiReview, {}),
  });
}

/** Start the read before the page mounts (a route loader); the hook then joins it. */
export function prefetchFigiReview(client: QueryClient): void {
  void client.query(figiReviewQuery()).catch(() => undefined);
}

/** Null: nothing stored. */
export function useFigiReview() {
  return useQuery({
    ...figiReviewQuery(),
    select: (data) => data.figiReview,
  });
}

function leveragedReviewQuery() {
  return queryOptions({
    queryKey: queryKeys.gql('LeverageReview', {}),
    queryFn: () => gql(LeverageReview, {}),
  });
}

/** Start the read before the page mounts (a route loader); the hook then joins it. */
export function prefetchLeveragedReview(client: QueryClient): void {
  void client.query(leveragedReviewQuery()).catch(() => undefined);
}

/** Null: nothing stored. */
export function useLeveragedReview() {
  return useQuery({
    ...leveragedReviewQuery(),
    select: (data) => data.leverageReview,
  });
}
