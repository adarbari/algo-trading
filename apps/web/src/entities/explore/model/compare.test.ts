import { describe, expect, it } from 'vitest';

import { priceSeries, toCompared } from './compare';
import { isStale } from './freshness';

const served = [
  {
    instrumentId: 'EQ:A',
    symbol: 'AAPL',
    prices: {
      bars: [
        { session: '2025-10-02', close: 200 },
        { session: '2025-10-03', close: null },
        { session: '2025-10-06', close: 250 },
      ],
    },
  },
  { instrumentId: 'EQ:M', symbol: 'MSFT', prices: { bars: [] } },
];

describe('compare', () => {
  it('makes one series per ticker rebased to 100, skipping missing closes', () => {
    expect(priceSeries(toCompared(served))).toEqual([
      {
        id: 'AAPL',
        label: 'AAPL',
        points: [
          { time: '2025-10-02', value: 100 },
          { time: '2025-10-06', value: 125 },
        ],
      },
      { id: 'MSFT', label: 'MSFT', points: [] },
    ]);
  });

  it('calls a session stale after a long weekend', () => {
    expect(isStale('2026-10-02', '2026-10-05')).toBe(false);
    expect(isStale('2026-10-02', '2026-10-06')).toBe(false);
    expect(isStale('2026-10-02', '2026-10-07')).toBe(true);
  });
});
