/**
 * Every rule screener's track records (`Screener.trackRecords`, one per edge that lists it) and
 * the status of each edge, in one read (ADR 0053): the Screeners list's chip and the Ideas
 * screener rows' odds line both select from this one cached response.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

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
          liftPts
          sessions
          picks
        }
      }
    }
  }
`);

const trackRecordsQuery = () =>
  queryOptions({
    queryKey: queryKeys.gql('ScreenerTrackRecords', {}),
    queryFn: ({ queryKey }) => gql(ScreenerTrackRecords, {}, queryKey),
  });

/** Start reading every screener's track records before the page mounts (a route loader). */
export function prefetchTrackRecords(client: QueryClient): void {
  void client.query(trackRecordsQuery()).catch(() => undefined);
}

/** The track records of `screenerId` (empty: no edge lists it), one per edge, as served. */
export function useTrackRecords(screenerId: string) {
  return useQuery({
    ...trackRecordsQuery(),
    select: (data) => toTrackRecords(data).get(screenerId) ?? [],
  });
}
