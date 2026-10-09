/**
 * The status strip's one read (ADR 0037), one operation on every page: the session and every
 * screener the user sees with its run state for it (a run, or why none: NOT_RUN), nothing of the
 * picks, and, for an admin only (`@include(if: $admin)`: the API refuses them to anyone else),
 * the newest nightly run and the one-session completeness grid. It was four requests (screens,
 * nightly runs, completeness, and the viewer's) before; the viewer stays its own cached read. Not
 * `Query.ideas`: that ranks every screener's picks with their values (1.3 s of the API's
 * reads on every page, for what the strip never shows). Every viewer may read it; the nightly
 * run and the grid carry the same fields as the run and ingestion entities' own reads.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { Completeness } from '@/entities/ingestion';
import type { NightlyRun } from '@/entities/run';

import type { ScreenerStates } from '../model/issues';

const StatusStrip = graphql(`
  query StatusStrip($admin: Boolean!) {
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
    nightlyRuns(limit: 1) @include(if: $admin) {
      runId
      session
      status
      startedAt
      finishedAt
      durationS
      problems
      steps {
        name
        status
        durationS
        reason
        error
      }
    }
    completeness(sessions: 1) @include(if: $admin) {
      sessions
      datasets
      lastClosed
      cells {
        dataset
        session
        status
        present
        expected
        basis
        runIds
      }
    }
  }
`);

export interface StatusStripState {
  screens: ScreenerStates | null;
  nightly: NightlyRun | null;
  completeness: Completeness | null;
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
    }),
  });
}
