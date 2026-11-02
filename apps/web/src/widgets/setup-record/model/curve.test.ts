import { describe, expect, it } from 'vitest';

import { CURVE_FIXTURE, type EdgeCurve } from '@/entities/edge';

import { curveChart, curveFormat } from './curve';

const curve = CURVE_FIXTURE as unknown as EdgeCurve;

describe('curveChart', () => {
  it('draws the picks and the universe by exit session, not decision', () => {
    const { series } = curveChart(curve);
    expect(series.map((s) => s.id)).toEqual(['picks', 'base', 'live']);
    expect(series[0]?.points.map((p) => p.time)).toEqual([
      '2026-02-02',
      '2026-04-02',
      '2026-06-03',
    ]);
    expect(series[0]?.points.map((p) => p.value)).toEqual([0.01, 0.03, 0.02]);
    expect(series[1]?.points.map((p) => p.value)).toEqual([0.002, 0.004, 0.006]);
  });

  it('draws a decoy only when it is switched on, at its exits, beside the picks', () => {
    expect(curveChart(curve).series.map((s) => s.id)).not.toContain('decoy:size_small');
    const { series } = curveChart(curve, ['size_small']);
    const decoy = series.find((s) => s.id === 'decoy:size_small');
    expect(decoy?.label).toBe('size_small');
    expect(decoy?.points.map((p) => [p.time, p.value])).toEqual([
      ['2026-02-02', 0.004],
      ['2026-04-02', 0.007],
      ['2026-06-03', 0.005],
    ]);
    expect(curveChart(curve, ['not_a_decoy']).series.map((s) => s.id)).toEqual(
      curveChart(curve).series.map((s) => s.id),
    );
  });

  it('continues the picks with a dashed paper stroke from the served anchor', () => {
    const live = curveChart(curve).series[2];
    expect(live?.stroke).toBe('dashed');
    expect(live?.points).toEqual([
      { time: '2026-08-03', value: 0.02 },
      { time: '2026-09-03', value: 0.024 },
      { time: '2026-10-02', value: 0.022 },
    ]);
  });

  it('marks each side of the split from the points own period, and the spans with no number as one lane', () => {
    const { bands, lanes } = curveChart(curve);
    expect(bands).toEqual([
      { start: '2026-02-02', end: '2026-04-02', tone: 'neutral', label: 'In-sample' },
      { start: '2026-06-03', end: '2026-06-03', tone: 'info', label: 'Out-of-sample' },
    ]);
    expect(lanes).toHaveLength(1);
    expect(lanes[0]?.segments).toEqual([
      { start: '2026-02-10', end: '2026-02-20', tone: 'neutral', label: 'Lost input' },
    ]);
  });

  it('has no bands for a run with no split, no base line without one, and no live stroke without points', () => {
    const plain = {
      ...curve,
      gaps: [],
      live: null,
      points: curve.points.map((p) => ({ ...p, period: 'all', baseCumulative: null })),
    } as unknown as EdgeCurve;
    const chart = curveChart(plain);
    expect(chart.bands).toEqual([]);
    expect(chart.lanes).toEqual([]);
    expect(chart.series.map((s) => s.id)).toEqual(['picks']);
  });

  it('plots one value a day when two windows are known the same day', () => {
    const [first, second] = curve.points;
    const doubled = {
      ...curve,
      points: [first, { ...second, exit: first?.exit }],
    } as unknown as EdgeCurve;
    expect(curveChart(doubled).series[0]?.points).toHaveLength(1);
  });

  it('reads a return as a signed percent and excess wins as a signed count', () => {
    expect(curveFormat(curve)).toEqual({ kind: 'delta', unit: 'percent', digits: 1 });
    expect(curveFormat({ ...curve, kind: 'excess_wins' })).toEqual({
      kind: 'delta',
      unit: 'number',
      digits: 1,
    });
  });
});
