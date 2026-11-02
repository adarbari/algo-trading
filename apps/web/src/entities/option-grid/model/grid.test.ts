import { describe, expect, it } from 'vitest';

import {
  bandLabel,
  detailFigures,
  heatLevel,
  gridOf,
  gridUnknown,
  gridView,
  type OptionGrid,
} from './grid';

const UNKNOWN = { code: 'NOT_STORED', kind: 'NOT_STORED', guideTerm: 'x', kindText: 'Not stored' };
const CELL = {
  __typename: 'GridCell',
  band: 0.1,
  strike: 95,
  delta: -0.1,
  iv: 0.3,
  mid: 1.2,
  roc: 0.0126,
  yieldAnn: 0.184,
  breakeven: 93.8,
  pBelow: 0.12,
  spreadPct: 0.05,
  openInterest: null,
} as const;

const GRID = {
  __typename: 'OptionGrid',
  underlyingId: 'EQ:X',
  session: '2026-10-30',
  pricedAt: 100,
  qKnown: true,
  bands: [0.1, 0.2],
  columns: [
    {
      bucket: 30,
      expiry: '2026-11-20',
      days: 21,
      reportInside: true,
      reportInsideUnknown: null,
      gap: null,
    },
    {
      bucket: 60,
      expiry: null,
      days: null,
      reportInside: null,
      reportInsideUnknown: null,
      gap: UNKNOWN,
    },
  ],
  // [column][band]
  puts: [
    [CELL, { __typename: 'Unknown', ...UNKNOWN }],
    [
      { __typename: 'Unknown', ...UNKNOWN },
      { __typename: 'Unknown', ...UNKNOWN },
    ],
  ],
  calls: [[], []],
} as unknown as OptionGrid;

describe('option grid model', () => {
  it('lays a side out as rows by band across the expiry columns', () => {
    const view = gridView(GRID, 'puts');
    expect(view.rows.map((r) => r.label)).toEqual(['0.10', '0.20']);
    expect(view.columns.map((c) => c.label)).toEqual(['Fri 20 Nov', '60 days']);
    expect(view.rows[0]?.cells['30']).toMatchObject({ kind: 'cell', text: '18.4%', level: 2 });
    expect(view.rows[1]?.cells['30']).toMatchObject({ kind: 'unknown' });
    expect(view.columns[0]?.reportInside).toBe(true);
  });

  it('keeps an unknown cell and a column gap as the public kind, never a blank', () => {
    const view = gridView(GRID, 'puts');
    expect(view.rows[0]?.cells['60']).toMatchObject({
      kind: 'unknown',
      unknown: { kindText: 'Not stored' },
    });
    expect(view.rows[1]?.cells['60']).toMatchObject({ kind: 'unknown' });
  });

  it('shows an unknown open interest as a dash, not zero', () => {
    const lines = Object.fromEntries(detailFigures(CELL).map((f) => [f.term, f.value]));
    expect(lines['open_interest']).toBe('—');
    expect(lines['grid_strike']).toBe('$95.00');
  });

  it('tells a grid from why there is none', () => {
    expect(gridOf({ optionGrid: GRID } as never)).toBe(GRID);
    const why = { __typename: 'Unknown', ...UNKNOWN };
    expect(gridOf({ optionGrid: why } as never)).toBeNull();
    expect(gridUnknown({ optionGrid: why } as never)).toBe(why);
    expect(bandLabel(0.125)).toBe('0.13');
  });
});

describe('heat level', () => {
  it('grades a yield by thirds of the shown range', () => {
    expect([0.0, 0.1, 0.3].map((v) => heatLevel(v, [0, 0.1, 0.3]))).toEqual([1, 2, 3]);
    expect(heatLevel(0.2, [0.2])).toBe(2);
  });
});
