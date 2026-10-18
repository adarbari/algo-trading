import { describe, expect, it } from 'vitest';

import { factItem, type FactSpec } from './fact';
import type { ServedValue } from './value';

const served = (
  name: string,
  value: number,
  format: string,
  unit: string | null,
  dtype = 'float',
): ServedValue =>
  ({ name, value, unknown: null, info: { format, unit, dtype } }) as unknown as ServedValue;

const spec = (name: string): FactSpec => ({ id: 'x', label: 'X', name, signed: true }) as FactSpec;
const read = (value: ServedValue) =>
  factItem(new Map([[value.name, value]]), spec(value.name))?.format;

describe('factItem signed formats', () => {
  it('signs a fraction as a percent change', () => {
    expect(read(served('a', 0.05, 'PERCENT', 'decimal'))).toEqual({
      kind: 'delta',
      unit: 'percent',
    });
  });

  it('signs a value in percentage points as points with one decimal, not rescaled', () => {
    expect(read(served('a', 3.2, 'NUMBER', 'pct_points'))).toEqual({
      kind: 'delta',
      unit: 'points',
      digits: 1,
    });
  });

  it('signs a dollar difference and a count change', () => {
    expect(read(served('a', 0.05, 'CURRENCY', 'usd'))).toEqual({
      kind: 'delta',
      unit: 'number',
      digits: 2,
    });
    expect(read(served('a', 2, 'NUMBER', 'count', 'int64'))).toEqual({
      kind: 'delta',
      unit: 'number',
      digits: 0,
    });
  });
});
