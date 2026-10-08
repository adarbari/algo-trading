/**
 * The instrument's facts for one session over GraphQL (ADR 0037): who it is (typed identity)
 * and the catalogue features asked for by name (ADR 0038), each a value or UNKNOWN with the
 * server's reason, plus the session they are all for (and what it is missing).
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type SiteFeature } from '@/shared/api';

const InstrumentFacts = graphql(`
  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {
    session {
      date
      isLatest
      unavailable {
        kind
        features
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
      referenceSnapshot
      preSnapshot
    }
    instrument(key: $key) {
      instrumentId
      symbol
      name
      securityType
      exchange
      isEtf
      description
      referenceSnapshot
      features(names: $names) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
    }
  }
`);

/**
 * `names` of the instrument `key` (a ticker or an id) for the latest session. The PR that adds
 * a `date` here must also bound the events the Overview pairs with it (`earningsOn`) to what
 * was known by that session, or a later revision of a report leaks into a past view.
 */
export function useInstrumentFacts(key: string | null, names: readonly SiteFeature[]) {
  const variables = { key: key ?? '', names: [...names] };
  return useQuery({
    queryKey: queryKeys.gql('InstrumentFacts', variables),
    queryFn: () => gql(InstrumentFacts, variables),
    enabled: Boolean(key),
  });
}
