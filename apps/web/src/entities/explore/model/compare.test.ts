import { describe, expect, it } from 'vitest';

import { priceSeries, rowValues, type FeatureComparison, type PriceComparison } from './compare';
import { isStale } from './freshness';

const prices: PriceComparison = {
  instruments: [
    { instrument_id: 'EQ:A', symbol: 'AAPL' },
    { instrument_id: 'EQ:M', symbol: null },
  ],
  adjustment: 'splits',
  rebase: 100,
  start: '2025-10-02',
  end: '2025-10-06',
  dates: ['2025-10-02', '2025-10-03', '2025-10-06'],
  series: { 'EQ:A': [100, null, 101.5], 'EQ:M': [100, 99, 98] },
};

describe('compare', () => {
  it('makes one chart series per ticker, skipping missing closes', () => {
    expect(priceSeries(prices)).toEqual([
      {
        id: 'AAPL',
        label: 'AAPL',
        points: [
          { time: '2025-10-02', value: 100 },
          { time: '2025-10-06', value: 101.5 },
        ],
      },
      {
        id: 'EQ:M',
        label: 'EQ:M',
        points: [
          { time: '2025-10-02', value: 100 },
          { time: '2025-10-03', value: 99 },
          { time: '2025-10-06', value: 98 },
        ],
      },
    ]);
  });

  it('reads a feature row by ticker', () => {
    const compared: FeatureComparison = {
      session: '2026-10-02',
      instruments: prices.instruments,
      missing: [],
      rows: [{ feature: 'feature.market_cap', dtype: 'float', values: { 'EQ:A': 4.87e12 } }],
    };
    expect(rowValues(compared, 'feature.market_cap')).toEqual({ AAPL: 4.87e12, 'EQ:M': undefined });
    expect(rowValues(compared, 'unknown')).toEqual({ AAPL: undefined, 'EQ:M': undefined });
  });

  it('calls a session stale after a long weekend', () => {
    expect(isStale('2026-10-02', '2026-10-05')).toBe(false);
    expect(isStale('2026-10-02', '2026-10-06')).toBe(false);
    expect(isStale('2026-10-02', '2026-10-07')).toBe(true);
  });
});
