import { describe, expect, it } from 'vitest';

import { criterionLines } from './criteria-lines';

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
