import { describe, expect, it } from 'vitest';

import { periodOf } from './period';

const f = (id: string, ...values: string[]) => ({ id, values, active: true });

describe('periodOf', () => {
  it('reads the old four periods off the record and in-sample filters', () => {
    expect(periodOf([])).toBe('ALL');
    expect(periodOf([f('record', 'live')])).toBe('LIVE');
    expect(periodOf([f('record', 'backtest'), f('in_sample', 'yes')])).toBe('IN_SAMPLE');
    expect(periodOf([f('in_sample', 'no')])).toBe('OUT_OF_SAMPLE');
  });

  it('keeps the backtest default when the viewer asked for both records or switched a filter off', () => {
    expect(periodOf([f('record', 'backtest', 'live'), f('in_sample', 'yes')])).toBe('ALL');
    expect(periodOf([{ ...f('in_sample', 'no'), active: false }])).toBe('ALL');
    expect(periodOf([f('result', 'won')])).toBe('ALL');
  });
});
