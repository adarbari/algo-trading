/**
 * What the list under the price chart needs in one request (`Instrument.events` and
 * `Instrument.eventStudy`, ADR 0050): every stored event with its source page and whether it is
 * the company's own 8-K report, and the study's dated events and 8-Ks with theirs. A document of
 * its own, so the chart's queries on the Explore page's first load do not carry the extra
 * fields.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const InstrumentEventList = graphql(`
  query InstrumentEventList($key: String!) {
    instrument(key: $key) {
      instrumentId
      events {
        table
        kind
        date
        ts
        values
        sourceUrl
        confirmed
      }
      eventStudy {
        session
        ahead {
          date
          time
          kind
          label
          sourceUrl
        }
        filings {
          filingDate
          form
          label
          sourceUrl
        }
      }
    }
  }
`);

type Instrument = NonNullable<gqlTypes.InstrumentEventListQuery['instrument']>;
/** A stored event with the server's source page and confirmed flag. */
export type EventRow = Instrument['events'][number];
/** The event study with its source pages. */
export type EventStudyLinks = NonNullable<Instrument['eventStudy']>;

/** The stored events and the study of `key` (a ticker); null: no such ticker. */
export function useInstrumentEventList(key: string | null) {
  const variables = { key: key ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('InstrumentEventList', variables),
    queryFn: ({ queryKey }) => gql(InstrumentEventList, variables, queryKey),
    select: (data: gqlTypes.InstrumentEventListQuery) => data.instrument,
    enabled: Boolean(key),
  });
}
