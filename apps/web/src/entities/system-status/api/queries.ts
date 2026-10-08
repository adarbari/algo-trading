/**
 * The status strip's one extra read (ADR 0037): `Query.ideas` with `limit: 1`, for what the
 * screeners say about the latest session (a run, or why none: NOT_RUN) without the picks. Every
 * viewer may read it; the nightly run, which only admins may read, comes from the run entity.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const StatusScreens = graphql(`
  query StatusScreens {
    ideas(limit: 1) {
      session
      screeners {
        screener {
          id
          name
        }
        notRun {
          code
          kindText
        }
      }
    }
  }
`);

/** The latest session's screeners with their run state; null `ideas`: nothing stored yet. */
export function useScreenerStates() {
  return useQuery({
    queryKey: queryKeys.gql('StatusScreens', {}),
    queryFn: () => gql(StatusScreens, {}),
    select: (data) => data.ideas,
  });
}
