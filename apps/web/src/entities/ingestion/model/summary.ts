/**
 * The headline of the completeness grid for its latest session: the share of expected rows
 * present (over datasets with an expectation), how many datasets are complete / partial /
 * failed, and whether the store is stale (the exchange closed a later session).
 */
import { cellShare, cellStatuses } from './grid';
import type { Completeness } from './types';

export interface CompletenessSummary {
  session: string;
  /** Present / expected rows over the session's datasets with an expectation, 0..1 (null: none). */
  share: number | null;
  datasets: number;
  complete: number;
  partial: number;
  failed: number;
  notCollected: number;
}

export function completenessSummary(completeness: Completeness): CompletenessSummary | null {
  const session = completeness.sessions.at(-1);
  if (!session) return null;
  const cells = completeness.cells.filter((c) => c.session === session);
  const statuses = cellStatuses(completeness);
  const count = (status: string) =>
    cells.filter((c) => statuses.get(`${c.dataset}|${session}`) === status).length;
  const expected = cells.filter((c) => cellShare(c) !== null);
  const wanted = expected.reduce((sum, c) => sum + (c.expected ?? 0), 0);
  const present = expected.reduce((sum, c) => sum + Math.min(c.present, c.expected ?? 0), 0);
  return {
    session,
    share: wanted > 0 ? present / wanted : null,
    datasets: cells.length,
    complete: count('complete'),
    partial: count('partial'),
    failed: count('failed'),
    notCollected: count('not-collected'),
  };
}

/** The latest stored session when the exchange has closed a later one (else null). */
export function staleSince(completeness: Completeness): string | null {
  const latest = completeness.sessions.at(-1);
  return latest !== undefined && latest < completeness.last_closed ? latest : null;
}
