/**
 * The edges that list one screener and each one's frozen-period record (`Screener.trackRecords`
 * with the edge's status, ADR 0053): the edge line of the screener's page. One read for the page;
 * the Screeners list reads every screener's records in `track-records.ts` instead.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { screenerEdges } from '../model/screener-edges';

const ScreenerEdges = graphql(`
  query ScreenerEdges($id: String!) {
    edges {
      id
      status
    }
    screener(id: $id) {
      id
      trackRecords {
        screenerId
        edgeId
        edgeName
        runLabel
        splitFrom
        afterSession
        notRun {
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
        horizons {
          horizonSessions
          hitRate
          baseRate
          liftPts
          sessions
          picks
        }
      }
    }
  }
`);

/** The edges of screener `id`, strongest first (empty: no edge lists it). */
export function useScreenerEdges(id: string) {
  const variables = { id };
  return useQuery({
    queryKey: queryKeys.gql('ScreenerEdges', variables),
    queryFn: ({ queryKey }) => gql(ScreenerEdges, variables, queryKey),
    select: screenerEdges,
  });
}
