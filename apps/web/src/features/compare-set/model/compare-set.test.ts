import { describe, expect, it } from 'vitest';

import { MAX_COMPARE, nextSelection, seriesAt, seriesOf } from './compare-set';

describe('compare set', () => {
  it('keeps the pick order and appends new tickers', () => {
    expect(nextSelection(['AAPL', 'MSFT'], ['MSFT', 'AAPL', 'NVDA'])).toEqual([
      'AAPL',
      'MSFT',
      'NVDA',
    ]);
    expect(nextSelection(['AAPL', 'MSFT', 'NVDA'], ['NVDA', 'AAPL'])).toEqual(['AAPL', 'NVDA']);
    expect(nextSelection(['AAPL'], [])).toEqual([]);
  });

  it('holds at most six tickers, one per series colour', () => {
    const many = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
    expect(nextSelection([], many)).toHaveLength(MAX_COMPARE);
    expect(seriesAt(0)).toBe('s1');
    expect(seriesAt(5)).toBe('s6');
    expect(seriesAt(6)).toBeUndefined();
    expect(seriesOf(['AAPL', 'MSFT'], 'MSFT')).toBe('s2');
    expect(seriesOf(['AAPL'], 'KO')).toBeUndefined();
  });
});
