/**
 * Every rule screener's track records (`Screener.trackRecords`, one per edge that lists it) and
 * the status of each edge, in one read (ADR 0053): the Screeners list's chip and the Ideas
 * screener rows' odds line both select from this one cached response.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { toTrackRecords } from '../model/track-records';

const ScreenerTrackRecords = graphql(`
  query ScreenerTrackRecords {
    edges {
      id
      status
    }
    screeners {
      id
      trackRecords {
        screenerId
        edgeId
        edgeName
        runLabel
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
          lift
          sessions
          picks
        }
      }
    }
  }
`);

/** The track records of `screenerId` (empty: no edge lists it), one per edge, as served. */
export function useTrackRecords(screenerId: string) {
  return useQuery({
    queryKey: queryKeys.gql('ScreenerTrackRecords', {}),
    queryFn: () => gql(ScreenerTrackRecords, {}),
    select: (data) => toTrackRecords(data).get(screenerId) ?? [],
  });
}
