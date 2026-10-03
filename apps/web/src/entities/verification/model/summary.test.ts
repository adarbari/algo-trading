import { describe, expect, it } from 'vitest';

import { failedShare, failingChecks, statusCounts } from './summary';
import type { Verification } from './types';

// Shaped like the real run of 2026-10-02 (6 instruments, 2 FAIL on the low).
const run: Verification = {
  session: '2026-10-02',
  run_ids: ['verify_ibkr-2026-10-02-20261003T183522Z'],
  instruments: 6,
  counts: { PASS: 42, WARN: 0, FAIL: 2, NA: 12 },
  by_check: [{ check: 'low', counts: { PASS: 2, WARN: 0, FAIL: 2, NA: 0 } }],
  failing: [
    {
      instrument_id: 'EQ:BBG000BDTBL9',
      symbol: 'SPY',
      check: 'low',
      status: 'FAIL',
      ours: 680.5868,
      theirs: 682.68,
      diff: 0.003066,
      tolerance: 0.001,
      note: 'rel diff; worst session 2025-12-22 of 260 compared',
    },
  ],
};

describe('verification summary', () => {
  it('counts statuses and the failed share of graded checks', () => {
    expect(statusCounts({ ...run, counts: { PASS: 1 } })).toEqual({
      PASS: 1,
      WARN: 0,
      FAIL: 0,
      NA: 0,
    });
    expect(failedShare(run)).toBeCloseTo(2 / 44);
    expect(failedShare({ ...run, counts: { NA: 3 } })).toBeNull();
  });

  it('types the failing rows', () => {
    expect(failingChecks(run)).toEqual([
      {
        instrumentId: 'EQ:BBG000BDTBL9',
        symbol: 'SPY',
        check: 'low',
        status: 'FAIL',
        ours: 680.5868,
        theirs: 682.68,
        diff: 0.003066,
        tolerance: 0.001,
        note: 'rel diff; worst session 2025-12-22 of 260 compared',
      },
    ]);
    expect(
      failingChecks({ ...run, failing: [{ instrument_id: 'EQ:X', ours: 'n/a' }] })[0],
    ).toMatchObject({
      symbol: 'EQ:X',
      ours: null,
    });
  });
});
