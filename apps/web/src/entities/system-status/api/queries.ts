/**
 * The status strip's one read (ADR 0037), one operation on every page: the session and every
 * screener the user sees with its run state for it (a run, or why none: NOT_RUN), nothing of the
 * picks, and, for an admin only (`@include(if: $admin)`: the API refuses them to anyone else),
 * the newest nightly run and the one-session completeness grid. It was four requests (screens,
 * nightly runs, completeness, and the viewer's) before; the viewer stays its own cached read. Not
 * `Query.ideas`: that ranks every screener's picks with their values (1.3 s of the API's
 * reads on every page, for what the strip never shows). The session's `newer` (the incomplete
 * session left out, ADR 0062) feeds the session notice. Every viewer may read it; the nightly
 * run and the grid carry the same fields as the run and ingestion entities' own reads.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { CompletenessStatus, NightlyStatus, ScreenerStates } from '../model/issues';
import type { SessionNotice } from '../model/notice';

const StatusStrip = graphql(`
  query StatusStrip($admin: Boolean!) {
    session {
      date
      newer {
        date
        state
      }
    }
    screeners {
      id
      name
      notRun {
        code
        kindText
      }
    }
    nightlyRuns(limit: 1) @include(if: $admin) {
      runId
      session
      status
      problems
      steps {
        name
        status
      }
    }
    completeness(sessions: 1) @include(if: $admin) {
      sessions
      lastClosed
    }
  }
`);

export interface StatusStripState {
  screens: ScreenerStates | null;
  nightly: NightlyStatus | null;
  completeness: CompletenessStatus | null;
  /** The newer incomplete session the pages leave out (null: none); ADR 0062. */
  notice: SessionNotice | null;
}

/** What the strip draws from; `admin` adds the nightly run and the grid to the same request. */
export function useStatusStrip(admin: boolean) {
  return useQuery({
    queryKey: queryKeys.gql('StatusStrip', { admin }),
    queryFn: () => gql(StatusStrip, { admin }),
    select: (data): StatusStripState => ({
      screens: data.session
        ? {
            session: data.session.date,
            screeners: data.screeners.map(({ id, name, notRun }) => ({
              screener: { id, name },
              notRun,
            })),
          }
        : null,
      nightly: data.nightlyRuns?.[0] ?? null,
      completeness: data.completeness ?? null,
      notice: data.session?.newer ? data.session : null,
    }),
  });
}
