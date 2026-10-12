/**
 * The viewer's own missing-feature history (`Query.myFeatureRequests`, ADR 0066 amendment): the
 * features their Describe-it drafts listed as missing over the last year, one per feature. Their
 * own asks only: the server never sends another trader's, and no count across users exists.
 * Read when a draft names a missing feature, to say "you asked for this before, on Oct 3".
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const MyFeatureRequests = graphql(`
  query MyFeatureRequests {
    myFeatureRequests {
      ref
      description
      status
      unmapped
      firstAsked
      lastAsked
      timesAsked
      promotedTo
      feasibility
      span
      askedBeforeToday
    }
  }
`);

export type MyFeatureRequest = gqlTypes.MyFeatureRequestsQuery['myFeatureRequests'][number];

/** Off until a draft has something missing to compare against. */
export function useMyFeatureRequests(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.gql('MyFeatureRequests', {}),
    queryFn: () => gql(MyFeatureRequests, {}),
    select: (data) => data.myFeatureRequests,
    enabled,
    staleTime: 0, // the draft that just ran may have recorded a new ask
    retry: false,
  });
}
