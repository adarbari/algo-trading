/**
 * The status strip's one extra read (ADR 0037): the session and every screener the user sees
 * with its run state for it (a run, or why none: NOT_RUN), nothing of the picks. Not
 * `Query.ideas`: that ranks every screener's picks with their values (1.3 s of the API's
 * reads on every page, for what the strip never shows). Every viewer may read it; the nightly
 * run, which only admins may read, comes from the run entity.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { ScreenerStates } from '../model/issues';

const StatusScreens = graphql(`
  query StatusScreens {
    session {
      date
    }
    screeners {
      id
      name
      notRun {
        code
        kindText
      }
    }
  }
`);

/** The latest session's screeners with their run state; null: nothing stored yet. */
export function useScreenerStates() {
  return useQuery({
    queryKey: queryKeys.gql('StatusScreens', {}),
    queryFn: () => gql(StatusScreens, {}),
    select: (data): ScreenerStates | null =>
      data.session
        ? {
            session: data.session.date,
            screeners: data.screeners.map(({ id, name, notRun }) => ({
              screener: { id, name },
              notRun,
            })),
          }
        : null,
  });
}
