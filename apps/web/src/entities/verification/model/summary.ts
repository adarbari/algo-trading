/**
 * Reading a verification run: counts in status order (PASS, WARN, FAIL, NA), the share of
 * graded checks that failed (NA is not graded: either side had no value), and the failing rows
 * typed from the API's open-ended records.
 */
import type { FailingCheck, Verification } from './types';

export const VERIFY_STATUSES = ['PASS', 'WARN', 'FAIL', 'NA'] as const;
export type VerifyStatus = (typeof VERIFY_STATUSES)[number];

export function statusCounts(v: Verification): Record<VerifyStatus, number> {
  return Object.fromEntries(VERIFY_STATUSES.map((s) => [s, v.counts[s] ?? 0])) as Record<
    VerifyStatus,
    number
  >;
}

/** FAIL / (PASS + WARN + FAIL), or null when nothing was graded. */
export function failedShare(v: Verification): number | null {
  const c = statusCounts(v);
  const graded = c.PASS + c.WARN + c.FAIL;
  return graded > 0 ? c.FAIL / graded : null;
}

const num = (value: unknown): number | null => (typeof value === 'number' ? value : null);
const text = (value: unknown): string => (typeof value === 'string' ? value : '');

export function failingChecks(v: Verification): FailingCheck[] {
  return v.failing.map((row) => ({
    instrumentId: text(row['instrument_id']),
    symbol: text(row['symbol']) || text(row['instrument_id']),
    check: text(row['check']),
    status: text(row['status']),
    ours: num(row['ours']),
    theirs: num(row['theirs']),
    diff: num(row['diff']),
    tolerance: num(row['tolerance']),
    note: text(row['note']),
  }));
}
