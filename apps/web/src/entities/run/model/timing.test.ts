import { describe, expect, it } from 'vitest';

import { incompleteSteps, isReused, stepTimings } from './timing';
import type { NightlyRun } from './types';

const step = (name: string, status: string, durationS: number | null) => ({
  name,
  status,
  durationS,
  reason: null,
  error: null,
  counts: {},
  origin: null,
  originStartedAt: null,
  originDurationS: null,
});

const reused = (name: string, originDurationS: number | null) => ({
  ...step(name, 'SUCCEEDED', 0),
  origin: 'nightly-earlier',
  originStartedAt: '2026-10-03T03:46:00Z',
  originDurationS,
});

const run: NightlyRun = {
  runId: 'nightly-2026-10-02',
  session: '2026-10-02',
  status: 'partial',
  startedAt: '2026-10-03T09:00:00Z',
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
    const adr39 = { ...run, steps: [step('bars', 'SUCCEEDED', 1), step('rollups', 'NOT_RUN', 0)] };
    expect(incompleteSteps(adr39)).toEqual(['rollups']);
  });
});

describe('a resumed attempt', () => {
  const resumed: NightlyRun = {
    ...run,
    steps: [
      reused('macro', 0.4),
      step('rollups', 'SUCCEEDED', 60),
      reused('filings', 200),
      step('bars', 'SUCCEEDED', 20),
    ],
  };

  it('lists what it ran now first, then what it reused, each longest first', () => {
    expect(stepTimings(resumed).map((t) => t.name)).toEqual([
      'rollups',
      'bars',
      'filings',
      'macro',
    ]);
  });

  it("shares only this attempt's work among the steps it ran", () => {
    const [rollups, bars, filings] = stepTimings(resumed);
    expect(rollups?.share).toBeCloseTo(0.75);
    expect(bars?.share).toBeCloseTo(0.25);
    expect(filings && isReused(filings) && filings.share).toBe(0);
    expect(filings?.originDurationS).toBe(200);
  });

  it('keeps a reused step whose earlier record is gone, with no duration there', () => {
    const [t] = stepTimings({ ...run, steps: [reused('macro', null)] });
    expect(t && isReused(t)).toBe(true);
    expect(t?.originDurationS).toBeNull();
  });
});
