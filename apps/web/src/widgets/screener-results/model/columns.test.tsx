import { describe, expect, it } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';
import type { ScreenTable, ScreenTableRow } from '@/entities/screen';

import { resultColumns } from './columns';

const feature = (name: string, unit: string): CatalogueFeature =>
  ({
    name,
    unit,
    dtype: 'float64',
    description: name,
    kind: 'expression',
    scope: 'site',
  }) as CatalogueFeature;

const CATALOGUE = new Map([
  ['rollup.iv30@v1.iv30', feature('rollup.iv30@v1.iv30', 'decimal')],
  ['feature.market_cap', feature('feature.market_cap', 'usd')],
]);

const table = {
  criteria: [
    { criterion_id: 'optionable', field: 'instrument.optionable', mode: 'hard' },
    { criterion_id: 'iv30', field: 'rollup.iv30@v1.iv30', mode: 'hard' },
  ],
  column_names: ['spread'],
  feature_columns: ['feature.market_cap'],
} as unknown as ScreenTable;

const row = (outcome: string): ScreenTableRow => ({
  rank: 1,
  instrument_id: 'EQ:A',
  symbol: 'A',
  name: 'Agilent',
  decision: 'QUALIFIED',
  score: 90,
  reasons: '',
  flags: [],
  change: null,
  previous_decision: null,
  criteria: { iv30: { value: 0.307, outcome } },
  columns: { spread: 0.11 },
  features: { 'feature.market_cap': 5e10 },
});

describe('resultColumns', () => {
  const columns = resultColumns(table, CATALOGUE);

  it('layers the fixed, criterion, display and added columns, the ids being the API sort keys', () => {
    expect(columns.map((c) => c.id)).toEqual([
      'rank',
      'symbol',
      'decision',
      'score',
      'criterion:iv30', // the optionable gate has no column
      'column:spread',
      'feature.market_cap',
      'flags',
      'reasons',
    ]);
  });

  it('reads each value in the catalogue unit and tints a near miss or a miss', () => {
    const iv30 = columns.find((c) => c.id === 'criterion:iv30');
    expect(iv30?.format).toEqual({ kind: 'percent' });
    expect(iv30?.value(row('PASS'))).toBe(0.307);
    expect([
      iv30?.fill?.(row('PASS')),
      iv30?.fill?.(row('NEAR')),
      iv30?.fill?.(row('FAIL')),
    ]).toEqual([undefined, 'warning', 'negative']);
    expect(columns.find((c) => c.id === 'feature.market_cap')?.value(row('PASS'))).toBe(5e10);
  });
});
