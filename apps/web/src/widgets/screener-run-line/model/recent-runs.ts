/**
 * A screener's recent runs as the run line and the strip say them (GraphQL `Screener.recentRuns`).
 * The server decides each session's state, its counts and what it left out; this only words
 * them (a count the server did not store is left out of the line, never shown as 0). Pure.
 */
import type { RecentRun } from '@/entities/screen';

const STATE_WORD: Record<RecentRun['state'], string> = {
  COMPLETE: 'Complete',
  PARTIAL: 'Partial',
  NOT_RUN: 'Not run',
};

const TONE = { COMPLETE: 'positive', PARTIAL: 'warning', NOT_RUN: 'muted' } as const;

const count = (n: number) => n.toLocaleString('en-US');
const percent = (share: number) =>
  share.toLocaleString('en-US', { style: 'percent', maximumFractionDigits: 0 });

/** "Oct 22" from an ISO day (no time zone: the day as stored). */
function dayWord(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(Date.UTC(year ?? 0, (month ?? 1) - 1, day ?? 1)).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

/** The squares of the strip, oldest first: each labelled with its day, state and picks. */
export function stripItems(runs: readonly RecentRun[]) {
  return runs.map((run) => ({
    label:
      run.picked === null
        ? `${dayWord(run.session)}: ${STATE_WORD[run.state]}`
        : `${dayWord(run.session)}: ${STATE_WORD[run.state]}, ${count(run.picked)} picked`,
    tone: TONE[run.state],
    current: run.served,
  }));
}

/** The pieces of the run line for one session's run (a session that did not run has none). */
export interface RunLineParts {
  session: string;
  state: RecentRun['state'];
  version: string | null;
  picked: string | null;
  changes: string | null;
  leftOut: string | null;
}

export function runLineParts(run: RecentRun): RunLineParts {
  const changed = run.newPicks !== null && run.dropped !== null;
  return {
    session: run.session,
    state: run.state,
    version: run.configVersion === null ? null : `v${String(run.configVersion)}`,
    picked: run.picked === null ? null : `${count(run.picked)} picked`,
    changes: changed
      ? `+${count(run.newPicks ?? 0)} new, −${count(run.dropped ?? 0)} dropped`
      : null,
    leftOut:
      run.leftOutShare === null || run.leftOutShare === 0
        ? null
        : `Missing data for ${percent(run.leftOutShare)} of names`,
  };
}
