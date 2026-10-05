import { describe, expect, it } from 'vitest';

import { incompleteSteps, stepTimings } from './timing';
import type { NightlyRun } from './types';

const step = (name: string, status: string, durationS: number | null) => ({
  name,
  status,
  durationS,
  reason: null,
  error: null,
  counts: {},
});

const run: NightlyRun = {
  runId: 'nightly-2026-10-02',
  session: '2026-10-02',
  status: 'partial',
  startedAt: '2026-10-03T09:00:00Z',
  finishedAt: '2026-10-03T09:26:00Z',
  durationS: 1560,
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
