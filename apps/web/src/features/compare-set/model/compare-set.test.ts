import { describe, expect, it } from 'vitest';

import { MAX_COMPARE, seriesAt, seriesOf } from './compare-set';

describe('compare set', () => {
  it('gives each of at most six tickers one series colour, by position', () => {
    expect(MAX_COMPARE).toBe(6);
    expect(seriesAt(0)).toBe('s1');
    expect(seriesAt(5)).toBe('s6');
    expect(seriesAt(6)).toBeUndefined();
    expect(seriesOf(['AAPL', 'MSFT'], 'MSFT')).toBe('s2');
    expect(seriesOf(['AAPL'], 'KO')).toBeUndefined();
  });
});
