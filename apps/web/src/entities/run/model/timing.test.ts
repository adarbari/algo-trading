import { describe, expect, it } from 'vitest';

import { incompleteSteps, stepTimings } from './timing';
import type { NightlyRun } from './types';

const step = (name: string, status: string, duration_s: number | null) => ({
  name,
  status,
  duration_s,
  reason: null,
  error: null,
  counts: {},
});

const run: NightlyRun = {
  run_id: 'nightly-2026-10-02',
  session: '2026-10-02',
  status: 'partial',
  started_at: '2026-10-03T09:00:00Z',
  finished_at: '2026-10-03T09:26:00Z',
  duration_s: 1560,
  steps: [
    step('bars', 'COMPLETE', 0.5),
    step('chains', 'PARTIAL', 1200),
    step('rates', 'COMPLETE', 299.5),
    step('x', 'FAILED', null),
  ],
  problems: [],
};

describe('stepTimings', () => {
  it('orders steps by duration with their share', () => {
    const timings = stepTimings(run);
    expect(timings.map((t) => t.name)).toEqual(['chains', 'rates', 'bars']);
    expect(timings[0]?.share).toBeCloseTo(0.8);
  });

  it('lists the steps that did not complete', () => {
    expect(incompleteSteps(run)).toEqual(['chains', 'x']);
  });
});
