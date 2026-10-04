/** The verification entity's types: the latest live verification of our data vs IBKR. */
import type { components } from '@/shared/api';

type Schemas = components['schemas'];

export type Verification = Schemas['Verification'];
export type CheckCounts = Schemas['CheckCounts'];

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
