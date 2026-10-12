import { describe, expect, it } from 'vitest';

import {
  appliedRows,
  dryRunStats,
  hasCriteria,
  inputsLine,
  sampleOf,
  type DraftFormula,
} from './review';

const formula = (run: Partial<DraftFormula['dry_run']> = {}): DraftFormula => ({
  name: 'draft_near_high',
  expr: 'close / high_52w - 1',
  dtype: 'float',
  unit: 'ratio',
  description: 'How near the 52-week high',
  null_meaning: 'no price',
  inputs: ['close', 'high_52w'],
  criterion: null,
  fingerprint: 'abc',
  pending: true,
  dry_run: {
    rows: 13334,
    no_value_rate: 0.062,
    minimum: -0.97,
    maximum: 0,
    criterion_pass: 612,
    session: '2026-10-09',
    sample: [
      { instrument_id: 'EQ:A', value: -0.02 },
      { instrument_id: 'EQ:B', value: 'n/a' },
      { instrument_id: 'EQ:C', value: -0.1 },
      { instrument_id: 'EQ:D', value: -0.2 },
      { instrument_id: 'EQ:E', value: -0.3 },
      { instrument_id: 'EQ:F', value: -0.4 },
    ],
    ...run,
  },
});

describe('appliedRows', () => {
  it('lists each criterion with the field it reads and skips a row without one', () => {
    expect(
      appliedRows({
        criteria: { price: { field: 'f.close' }, odd: { op: 'gte' }, vol: { field: 'f.v' } },
      }),
    ).toEqual([
      { id: 'price', field: 'f.close' },
      { id: 'vol', field: 'f.v' },
    ]);
    expect(appliedRows({})).toEqual([]);
  });
});

describe('hasCriteria', () => {
  it('is false for a document with no criteria, so an empty draft is never loaded', () => {
    expect(hasCriteria({ id: 'x' })).toBe(false);
    expect(hasCriteria({ id: 'x', criteria: {} })).toBe(false);
    expect(hasCriteria({ id: 'x', criteria: { a: { field: 'f' } } })).toBe(true);
  });
});

describe('formula card', () => {
  it('says the inputs and the unit on one line', () => {
    expect(inputsLine(formula())).toBe('Inputs: close, high_52w · ratio');
    expect(inputsLine({ ...formula(), inputs: [], unit: '' })).toBe('');
  });

  it('lays the measured dry run out as figures and leaves out what was not measured', () => {
    const stats = dryRunStats(formula());
    expect(stats.map((s) => s.label)).toEqual(['Rows checked', 'No value', 'Range', 'Passing']);
    expect(stats[2]?.value).toBe('\u22120.970 to 0.000');
    const bare = dryRunStats(
      formula({ no_value_rate: null, minimum: null, maximum: null, criterion_pass: null }),
    );
    expect(bare.map((s) => s.label)).toEqual(['Rows checked']);
  });

  it('shows five sample rows, a value that is not a number as no value', () => {
    const sample = sampleOf(formula());
    expect(sample.rows).toHaveLength(5);
    expect(sample.rows[1]?.values['value']).toBeNull();
    expect(sample.columns[0]?.header).toBe('draft_near_high');
  });
});
