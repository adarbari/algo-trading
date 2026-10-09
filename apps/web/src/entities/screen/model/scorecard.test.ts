import { describe, expect, it } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';

import { scorecardRows } from './scorecard';
import type { Criterion } from './spec';

const feature = (name: string, unit: string | null, dtype = 'float64'): CatalogueFeature =>
  ({ name, unit, dtype, categories: [] }) as unknown as CatalogueFeature;

const FEATURES = new Map([
  ['feature.iv_hv_ratio', feature('feature.iv_hv_ratio', 'ratio')],
  ['rollup.iv30@v1.iv30', feature('rollup.iv30@v1.iv30', 'decimal')],
]);
const RULES = new Map<string, Criterion>([
  ['ratio', { id: 'ratio', field: 'feature.iv_hv_ratio', op: 'gte', value: 1.25, mode: 'soft' }],
]);

describe('scorecardRows', () => {
  it('formats the value and the served distance with the field format, and names the rule', () => {
    const [row] = scorecardRows(
      [
        {
          id: 'ratio',
          field: 'feature.iv_hv_ratio',
          outcome: 'NEAR',
          value: 3.9812825006854156,
          distance: 0.9812830000000001,
        },
      ],
      FEATURES,
      RULES,
    );
    expect(row?.value).toBe('3.98');
    expect(row?.distance).toBe('0.98');
    expect(row?.rule).toBe('≥ 1.25×');
    expect(row?.outcome).toBe('NEAR');
  });

  it('shows a dash for a missing value and no rule when the screen is unknown', () => {
    const [row] = scorecardRows(
      [{ id: 'iv30', field: 'rollup.iv30@v1.iv30', outcome: 'MISSING' }],
      FEATURES,
      new Map(),
    );
    expect(row).toMatchObject({ value: '—', rule: '', distance: null });
  });
});
