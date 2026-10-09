import { describe, expect, it } from 'vitest';

import { criterionLines, toCriteria } from './criteria-lines';

describe('toCriteria', () => {
  it('reads the typed criteria of a Screener: op and threshold as served, in order', () => {
    const criteria = toCriteria([
      { id: 'iv', field: 'rollup.iv@v1.iv_rank', mode: 'soft', op: 'gte', value: 50 },
      {
        id: 'band',
        field: 'rollup.price_stats@v2.close',
        mode: 'hard',
        op: 'between',
        value: [5, 10],
      },
      { id: 'has', field: 'instrument.sector', mode: 'hard', op: 'not_null', value: null },
    ]);
    expect(criteria).toEqual([
      { id: 'iv', field: 'rollup.iv@v1.iv_rank', mode: 'soft', op: 'gte', value: 50 },
      {
        id: 'band',
        field: 'rollup.price_stats@v2.close',
        mode: 'hard',
        op: 'between',
        value: [5, 10],
      },
      { id: 'has', field: 'instrument.sector', mode: 'hard', op: 'not_null' },
    ]);
    expect(criterionLines(criteria, new Map()).map((l) => l.rule)).toEqual([
      '≥ 50',
      'between 5 and 10',
      'has a value',
    ]);
  });

  it('is empty for a screener with none served', () => {
    expect(toCriteria(undefined)).toEqual([]);
  });
});

describe('criterionLines', () => {
  it('labels each criterion and reads its rule and mode', () => {
    const lines = criterionLines(
      [
        { id: 'a', field: 'rollup.iv@v1.iv_rank', op: 'gte', value: 50, mode: 'hard' },
        { id: 'b', field: 'instrument.optionable', op: 'not_null', mode: 'soft' },
      ],
      new Map(),
    );
    expect(lines.map((l) => [l.id, l.rule, l.mode])).toEqual([
      ['a', '≥ 50', 'hard'],
      ['b', 'has a value', 'soft'],
    ]);
    expect(lines[0]?.label).not.toBe('');
  });
});
