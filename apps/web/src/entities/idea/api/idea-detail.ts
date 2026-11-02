/**
 * One idea's page read (ADR 0083 amendment (b)): `idea(symbol, setup)` over GraphQL, the sections
 * filled by the server from the setup (why it is here, the historical exit rule, the evidence,
 * what could go wrong, the setup to learn). Null: the name is unknown, no setup picked it for the
 * session, or the setup asked for did not.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { toIdeaDetail } from '../model/idea-detail';

export const IDEA_DETAIL_OPERATION = 'IdeaDetail';

const IdeaDetailQuery = graphql(`
  query IdeaDetail($symbol: String!, $setup: String) {
    idea(symbol: $symbol, setup: $setup) {
      session
      instrumentId
      tab
      instrument {
        symbol
        name
      }
      setup {
        edgeId
        edgeName
        tab
        level
        place
      }
      setups {
        edgeId
        edgeName
        tab
        level
        place
      }
      why {
        thesis
        mechanism
        basisScreener
        decision
        criteria {
          id
          field
          mode
          outcome
          value
          distance
        }
        unknown {
          code
          kind
          guideTerm
          kindText
        }
      }
      exitRule {
        edgeId
        holdSessions
        winners
        inSampleOnly
        stop {
          kind
          fraction
          atr
          multiple
          winners
          beyond
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
      evidence {
        level
        result
        basis
        basisHorizon
        liftPts
        lift
        trades
        oosTrades
      }
      risks {
        persistence
        holdEnds
        watchOut
        events {
          date
          kind
          label
          name
        }
        unknown {
          code
          kind
          guideTerm
          kindText
        }
      }
      learn
    }
  }
`);

function options(symbol: string, setup: string | undefined) {
  const variables = { symbol, ...(setup && { setup }) };
  return queryOptions({
    queryKey: queryKeys.gql(IDEA_DETAIL_OPERATION, variables),
    queryFn: ({ queryKey }) => gql(IdeaDetailQuery, { setup: null, ...variables }, queryKey),
    select: toIdeaDetail,
  });
}

/** One idea's page for the latest session (null: it is not an idea tonight). */
export function useIdeaDetail(symbol: string, setup?: string) {
  return useQuery(options(symbol, setup));
}

/** Start the read before the page mounts (a route loader); the hook then joins it. */
export function prefetchIdeaDetail(client: QueryClient, symbol: string, setup?: string): void {
  void client.query(options(symbol, setup)).catch(() => undefined);
}
