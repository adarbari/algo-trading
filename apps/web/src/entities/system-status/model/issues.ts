/**
 * What is wrong with the system, as plain data for the status strip: the newest nightly run
 * (failed or partial: admins only) and the screeners with no run for the latest session. Most
 * serious first. An issue's id says what it is about and changes when the cause does, so a
 * snooze ends with the cause. No JSX: the widget draws it.
 */
import { isStale } from '@/entities/explore';
import { staleSince, type Completeness } from '@/entities/ingestion';
import type { NightlyRun } from '@/entities/run';

export interface SystemIssue {
  id: string;
  severity: 'failing' | 'warning';
  title: string;
  detail?: string;
  /** In-app links that explain or fix it. */
  links: readonly { label: string; href: string }[];
}

export interface ScreenerState {
  screener: { id: string; name: string };
  notRun: { kindText: string } | null;
}

export interface ScreenerStates {
  session: string;
  screeners: readonly ScreenerState[];
}

/** Named in the strip up to this many; more are one grouped issue. */
export const NAMED_SCREENERS = 3;

const STEP_FAILED = new Set(['FAILED', 'ERROR']);

function nightlyIssue(run: NightlyRun): SystemIssue | null {
  const status = run.status.toUpperCase();
  if (status !== 'FAILED' && status !== 'PARTIAL') return null;
  const failed = run.steps.filter((s) => STEP_FAILED.has(s.status.toUpperCase()));
  const where = failed.length > 0 ? `: ${failed.map((s) => s.name).join(', ')}` : '';
  const issue: SystemIssue = {
    id: `nightly:${run.runId}:${status}`,
    severity: status === 'FAILED' ? 'failing' : 'warning',
    title: `Nightly run ${run.session} ${status.toLowerCase()}${where}`,
    links: [{ label: 'View run', href: '/admin/ingestion' }],
  };
  return run.problems.length > 0 ? { ...issue, detail: run.problems.join('; ') } : issue;
}

function screenerIssues(states: ScreenerStates): SystemIssue[] {
  const missing = states.screeners.filter((s) => s.notRun !== null);
  if (missing.length === 0) return [];
  if (missing.length > NAMED_SCREENERS) {
    return [
      {
        id: `screens:${states.session}:${missing.map((s) => s.screener.id).join(',')}`,
        severity: 'warning',
        title: `${missing.length} screeners have no run for ${states.session}`,
        links: [{ label: 'Open screeners', href: '/screeners' }],
      },
    ];
  }
  return missing.map(({ screener, notRun }) => ({
    id: `screen:${states.session}:${screener.id}`,
    severity: 'warning',
    title: `Screener "${screener.name}" has no run for ${states.session}`,
    ...(notRun ? { detail: notRun.kindText } : {}),
    links: [{ label: 'Open screener', href: `/screeners/${screener.id}` }],
  }));
}

function staleIssue(
  screens: ScreenerStates | null | undefined,
  completeness: Completeness | null | undefined,
): SystemIssue | null {
  // An admin's completeness grid says exactly which session the exchange closed without us;
  // everyone else gets the calendar rule on the session the pages read.
  const since = completeness ? staleSince(completeness) : null;
  const session = since ?? (screens && isStale(screens.session) ? screens.session : null);
  if (session === null) return null;
  return {
    id: `stale:${session}`,
    severity: 'warning',
    title: `Latest stored session is ${session}: a nightly run may have been missed`,
    links: [{ label: 'View runs', href: '/admin/ingestion' }],
  };
}

/** The open issues, failing ones first (each group keeps its order). */
export function systemIssues(
  nightly: NightlyRun | null | undefined,
  screens: ScreenerStates | null | undefined,
  completeness?: Completeness | null,
): SystemIssue[] {
  const all = [
    ...(nightly ? [nightlyIssue(nightly)] : []),
    staleIssue(screens, completeness),
    ...(screens ? screenerIssues(screens) : []),
  ].filter((i): i is SystemIssue => i !== null);
  return [
    ...all.filter((i) => i.severity === 'failing'),
    ...all.filter((i) => i.severity === 'warning'),
  ];
}
