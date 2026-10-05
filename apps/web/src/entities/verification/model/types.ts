/**
 * The verification entity's types: the latest session's live verification of our data vs
 * IBKR, as `Query.verification` serves it with its JSON (counts, failing rows) narrowed once
 * (`model/summary.ts`).
 */
import type { gqlTypes } from '@/shared/api';

export type ServedVerification = NonNullable<gqlTypes.VerificationQuery['verification']>;

/** Rows per status (PASS / WARN / FAIL / NA) of one check. */
export interface CheckCounts {
  check: string;
  counts: Readonly<Record<string, number>>;
}

export interface Verification extends Omit<ServedVerification, 'counts' | 'byCheck' | 'failing'> {
  counts: Readonly<Record<string, number>>;
  byCheck: CheckCounts[];
  failing: Readonly<Record<string, unknown>>[];
}

/** One failing (FAIL / WARN) row: our value, IBKR's, the difference and the tolerance. */
export interface FailingCheck {
  instrumentId: string;
  symbol: string;
  check: string;
  status: string;
  ours: number | null;
  theirs: number | null;
  diff: number | null;
  tolerance: number | null;
  note: string;
}
