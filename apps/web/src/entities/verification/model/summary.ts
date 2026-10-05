/**
 * Reading a verification run: the served JSON narrowed once (`toVerification`), counts in
 * status order (PASS, WARN, FAIL, NA), the share of graded checks that failed (NA is not
 * graded: either side had no value), and the failing rows typed from the API's open-ended
 * records.
 */
import type { CheckCounts, FailingCheck, ServedVerification, Verification } from './types';

export const VERIFY_STATUSES = ['PASS', 'WARN', 'FAIL', 'NA'] as const;
export type VerifyStatus = (typeof VERIFY_STATUSES)[number];

function record(value: unknown): Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function counts(value: unknown): Record<string, number> {
  return Object.fromEntries(
    Object.entries(record(value)).filter(
      (entry): entry is [string, number] => typeof entry[1] === 'number',
    ),
  );
}

/** The served verification with its counts and rows as records. */
export function toVerification(served: ServedVerification): Verification {
  return {
    ...served,
    counts: counts(served.counts),
    byCheck: served.byCheck.map((c): CheckCounts => ({ check: c.check, counts: counts(c.counts) })),
    failing: served.failing.map(record),
  };
}

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
