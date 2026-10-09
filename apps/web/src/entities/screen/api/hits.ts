/**
 * Which of the user's screeners picked one instrument in the latest session (GraphQL
 * `Instrument.screenerHits`, ADR 0037): each screener's run for exactly that session, and its
 * result for the instrument, with the criteria it was judged on. The Explore detail pane's
 * "Screener hits".
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const InstrumentScreenerHits = graphql(`
  query InstrumentScreenerHits($key: String!) {
    session {
      date
    }
    instrument(key: $key) {
      instrumentId
      symbol
      screenerHits {
        screener {
          id
          name
        }
        result {
          rank
          decision
          score
          reasons
          flags
          change
          criteria {
            id
            field
            mode
            outcome
            value
            distance
          }
        }
      }
    }
  }
`);

export type ScreenerHitsResponse = gqlTypes.InstrumentScreenerHitsQuery;

/** The screeners that picked `key` (a ticker) in the latest session; null: no such ticker. */
export function useScreenerHits(key: string | null) {
  const variables = { key: key ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('InstrumentScreenerHits', variables),
    queryFn: () => gql(InstrumentScreenerHits, variables),
    select: (data: ScreenerHitsResponse) =>
      data.instrument
        ? { session: data.session?.date ?? null, hits: data.instrument.screenerHits }
        : null,
    enabled: Boolean(key),
  });
}
