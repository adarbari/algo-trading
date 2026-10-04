import { describe, expect, it } from 'vitest';

import type { NarrowMiss } from '@/entities/screen';

import { missText } from './summary';

describe('missText', () => {
  it('names the symbol, the value, the threshold and the distance', () => {
    const miss = {
      instrument_id: 'EQ:1',
      criterion_id: 'iv',
      field: 'f',
      value: 0.48,
      threshold: 0.5,
      distance: 0.02,
      normalised: 0.4,
    } as NarrowMiss;
    expect(missText(miss, 'AAPL')).toBe('AAPL  0.480 vs 0.500, short by 0.020');
    expect(missText(miss, null)).toContain('EQ:1');
  });
});
