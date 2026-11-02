/**
 * The setups that picked one instrument tonight (ADR 0083 decision 2, `Instrument.pickedBy`): the
 * inverse of Ideas, each with its verdict level and its place in its tab's list. Empty: no setup
 * with a stored verdict of Works or Promising picked it. The cache holds the response.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const PickedBy = graphql(`
  query InstrumentPickedBy($key: String!) {
    instrument(key: $key) {
      instrumentId
      pickedBy {
        edgeId
        edgeName
        tab
        level
        place
      }
    }
  }
`);

export type PickingSetup = NonNullable<
  gqlTypes.InstrumentPickedByQuery['instrument']
>['pickedBy'][number];

/** The setups that picked `key` (a ticker or an id) for the latest session. */
export function usePickedBy(key: string | null) {
  const variables = { key: key ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('InstrumentPickedBy', variables),
    queryFn: ({ queryKey }) => gql(PickedBy, variables, queryKey),
    enabled: Boolean(key),
    select: (data) => data.instrument?.pickedBy ?? [],
  });
}
