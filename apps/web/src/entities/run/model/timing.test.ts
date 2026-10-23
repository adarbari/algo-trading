import { describe, expect, it } from 'vitest';

import { incompleteSteps, neighbours, relations, stepTimings } from './timing';
import type { NightlyRun, RunStep } from './types';

const step = (
  name: string,
  status: string,
  durationS: number | null,
  over: Partial<RunStep> = {},
): RunStep => ({
  name,
  status,
  durationS,
  reason: null,
  error: null,
  origin: null,
  originDurationS: null,
  startedAt: null,
  needs: [],
  rerunsAfter: [],
  ...over,
});

const reused = (name: string, originDurationS: number | null) =>
  step(name, 'SUCCEEDED', 0, { origin: 'nightly-earlier', originDurationS });

const run = (steps: RunStep[]): NightlyRun => ({
  runId: 'nightly-2026-10-02',
  session: '2026-10-02',
  status: 'partial',
  startedAt: '2026-10-03T09:00:00Z',
  durationS: 1560,
  steps,
  problems: [],
});

const plain = run([
  step('bars', 'COMPLETE', 0.5),
  step('chains', 'PARTIAL', 1200),
  step('rates', 'COMPLETE', 299.5),
  step('x', 'FAILED', null),
]);

describe('stepTimings', () => {
  it('puts failed first, then what ran longest first, with their share', () => {
    const timings = stepTimings(plain);
    expect(timings.map((t) => [t.name, t.state])).toEqual([
      ['chains', 'failed'],
      ['x', 'failed'],
      ['rates', 'ran'],
      ['bars', 'ran'],
    ]);
    expect(timings.find((t) => t.name === 'rates')?.share).toBeCloseTo(299.5 / 1500);
  });

  it('lists the steps that did not complete', () => {
    expect(incompleteSteps(plain)).toEqual(['chains', 'x']);
    const adr39 = run([step('bars', 'SUCCEEDED', 1), step('rollups', 'NOT_RUN', 0)]);
    expect(incompleteSteps(adr39)).toEqual(['rollups']);
  });

  it('tells all five states apart and shares only what ran now', () => {
    const timings = stepTimings(
      run([
        reused('macro', 0.4),
        step('rollups', 'NOT_RUN', 0),
        step('bars', 'WAITING', 90),
        step('chains', 'SUCCEEDED', 60),
        reused('filings', 200),
        step('screens', 'SKIPPED', 0),
        step('edge-signals', 'WAIVED', 0),
      ]),
    );
    expect(timings.map((t) => [t.name, t.state])).toEqual([
      ['chains', 'ran'],
      ['bars', 'waiting'],
      ['filings', 'reused'],
      ['macro', 'reused'],
      ['edge-signals', 'waived'],
      ['rollups', 'held'],
      ['screens', 'held'],
    ]);
    expect(timings.map((t) => t.share)).toEqual(
      [0.4, 0.6, 0, 0, 0, 0, 0].map((n) => expect.closeTo(n) as number),
    );
    expect(timings.find((t) => t.name === 'filings')?.originDurationS).toBe(200);
  });

  it('keeps a reused step whose earlier record is gone, with no duration there', () => {
    const [t] = stepTimings(run([reused('macro', null)]));
    expect(t?.state).toBe('reused');
    expect(t?.originDurationS).toBeNull();
  });
});

describe('relations', () => {
  const chain = stepTimings(
    run([
      step('bars', 'WAITING', 90),
      step('rollups', 'NOT_RUN', 0, { needs: ['bars'] }),
      step('screens', 'NOT_RUN', 0, { needs: ['rollups', 'chains'] }),
      step('chains', 'SUCCEEDED', 5),
      step('macro', 'SUCCEEDED', 1),
    ]),
  );

  it('marks what a step needs and holds back, transitively, and dims the rest', () => {
    const rel = relations(chain, 'rollups');
    expect([...rel]).toEqual(
      expect.arrayContaining([
        ['rollups', 'selected'],
        ['bars', 'upstream'],
        ['screens', 'downstream'],
        ['chains', 'dimmed'],
        ['macro', 'dimmed'],
      ]),
    );
    expect(relations(chain, 'screens').get('bars')).toBe('upstream');
  });

  it('marks nothing without a selection or when the run recorded no edges', () => {
    expect(relations(chain, null).size).toBe(0);
    const unrecorded = stepTimings(run([step('bars', 'SUCCEEDED', 1, { needs: null })]));
    expect(relations(unrecorded, 'bars').size).toBe(0);
  });

  it("lists a step's direct neighbours", () => {
    expect(neighbours(chain, 'rollups')).toEqual({ needs: ['bars'], holds: ['screens'] });
  });
});
