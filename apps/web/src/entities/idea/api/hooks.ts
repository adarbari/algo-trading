/**
 * The Ideas page's one read (ADR 0037): `IdeasPage` over GraphQL, the ranked ideas for the
 * latest session with every pick (the size each gets from the regime, ADR 0049), the picks the
 * regime gate paused with their reasons, the user's screeners with their run (or why not run) and
 * picked counts over the whole run, and each idea's facts by catalogue name (earnings, nearest
 * expiry, IV: ADR 0038). The cache holds the response; `select` shapes it.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { IDEA_FEATURES } from '../model/facts';
import { toIdeasData } from '../model/idea';

/** Ideas fetched per load (the API's default is 50, its maximum 1000). */
export const IDEAS_LIMIT = 200;

/** The GraphQL operation's name: its cached responses share this key prefix. */
export const IDEAS_OPERATION = 'IdeasPage';

const IdeasPage = graphql(`
  query IdeasPage($limit: Int!, $names: [FeatureName!]!) {
    ideas(limit: $limit) {
      session
      priority
      total
      pausedTotal
      paused {
        instrumentId
        instrument {
          symbol
        }
        result {
          configId
          score
          reasons
          regime
        }
      }
      screeners {
        screener {
          id
          name
          owner
          version
        }
        run {
          runId
          configVersion
          paused
        }
        notRun {
          code
          detail
          reason
        }
        picked
        top {
          instrumentId
          score
          instrument {
            symbol
          }
        }
      }
      items {
        rank
        instrumentId
        regime
        sizeMultiplier
        instrument {
          symbol
          features(names: $names) {
            name
            value
            unknown {
              code
              detail
            }
            info {
              format
              unit
              dtype
              nullMeaning
            }
          }
        }
        picks {
          configId
          decision
          score
          reasons
          flags
          criteria {
            id
            value
          }
          columns {
            name
            value
          }
        }
      }
    }
  }
`);

/** The latest session's ideas (null `ideas`: nothing stored yet). */
export function useIdeas() {
  const variables = { limit: IDEAS_LIMIT, names: [...IDEA_FEATURES] };
  return useQuery({
    queryKey: queryKeys.gql(IDEAS_OPERATION, variables),
    queryFn: () => gql(IdeasPage, variables),
    select: toIdeasData,
  });
}
