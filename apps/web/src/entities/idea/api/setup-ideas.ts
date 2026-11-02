/**
 * The Ideas tab's list from the picks of setups with a good stored verdict (ADR 0083 decision 2):
 * `setupIdeas(tab)` over GraphQL. The server decides which setups qualify, ranks and caps the
 * list; this hook only reads it. An `unproven` state means no setup of the tab qualifies and the
 * page shows the tab's pool of screeners instead.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { toSetupIdeas } from '../model/setup-ideas';
import { gqlTab, type IdeaTab } from '../model/search';

export const SETUP_IDEAS_OPERATION = 'SetupIdeas';

const SetupIdeasQuery = graphql(`
  query SetupIdeas($tab: IdeaTab!) {
    setupIdeas(tab: $tab) {
      session
      state
      ruleVersion
      total
      leftOut {
        kind
        count
      }
      groups {
        edgeId
        name
        level
        liftPts
        oosTrades
        basisScreener
        basisHorizon
        state
        picked
        shown
        unknown {
          code
          kind
          guideTerm
          kindText
        }
      }
      ideas {
        rank
        instrumentId
        setupId
        place
        watchOut
        instrument {
          symbol
          name
        }
        alsoIn {
          edgeId
          edgeName
          place
        }
        metrics {
          name
          value
        }
        result {
          decision
          regime
          sizeMultiplier
        }
      }
    }
  }
`);

function options(tab: IdeaTab) {
  const variables = { tab: gqlTab(tab) } as const;
  return queryOptions({
    queryKey: queryKeys.gql(SETUP_IDEAS_OPERATION, variables),
    queryFn: ({ queryKey }) => gql(SetupIdeasQuery, variables, queryKey),
    select: toSetupIdeas,
  });
}

/** The tab's list for the latest session (null: nothing stored). */
export function useSetupIdeas(tab: IdeaTab) {
  return useQuery(options(tab));
}

/** Start the read before the page mounts (a route loader); the hook then joins it. */
export function prefetchSetupIdeas(client: QueryClient, tab: IdeaTab): void {
  void client.query(options(tab)).catch(() => undefined);
}
