/**
 * What is coming for one instrument and what it filed, over GraphQL (`Instrument.eventStudy`,
 * ADR 0037 / 0050): the dated events of the next 90 days, its 8-Ks of the last 24 months, the
 * 7-90 day expiry ladder, a fund's reference and the parts not known for the session. One
 * query serves the Explore Events tab and the price chart's markers.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const InstrumentEventStudy = graphql(`
  query InstrumentEventStudy($key: String!) {
    session {
      date
    }
    instrument(key: $key) {
      instrumentId
      symbol
      eventStudy {
        session
        days
        months
        ahead {
          date
          time
          kind
          label
          name
          subjectId
          source
          knownFrom
          expiry
        }
        filings {
          accepted
          filingDate
          form
          items
          label
          knownFrom
        }
        ladder {
          expiry
          days
          clear
          marked
          spans {
            date
            time
            kind
            label
            name
            subjectId
            source
            knownFrom
            expiry
          }
        }
        reference {
          instrumentId
          symbol
          kind
          source
          status
        }
        gaps {
          instrumentId
          part
          unknown {
            code
            detail
            reason
          }
        }
      }
    }
  }
`);

export type EventStudyResponse = gqlTypes.InstrumentEventStudyQuery;

/** The study of `key` (a ticker) for the latest session; null: no such ticker. */
export function useInstrumentEventStudy(key: string | null) {
  const variables = { key: key ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('InstrumentEventStudy', variables),
    queryFn: () => gql(InstrumentEventStudy, variables),
    select: (data: EventStudyResponse) => data.instrument?.eventStudy ?? null,
    enabled: Boolean(key),
  });
}
