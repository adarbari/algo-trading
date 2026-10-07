import { describe, expect, it } from 'vitest';

import { historyOf, pointsOf, type FeatureHistory } from './values';

const history: FeatureHistory = {
  isPending: false,
  series: [
    {
      names: ['a', 'b'],
      points: [
        { session: '2026-10-01', values: [1, 'x'] },
        { session: '2026-10-02', values: [null, 3] },
        { session: '2026-10-05', values: [Number.NaN, 4] },
      ],
    },
  ],
};

describe('a feature history', () => {
  it('lists dated values with a gap for what is not a number', () => {
    expect(pointsOf(history, 'a')).toEqual([
      { time: '2026-10-01', value: 1 },
      { time: '2026-10-02', value: null },
      { time: '2026-10-05', value: null },
    ]);
    expect(pointsOf(history, 'b').map((p) => p.value)).toEqual([null, 3, 4]);
  });

  it('is empty for a feature no chunk has, as historyOf is null', () => {
    expect(pointsOf(history, 'c')).toEqual([]);
    expect(historyOf(history, 'c')).toBeNull();
  });
});
