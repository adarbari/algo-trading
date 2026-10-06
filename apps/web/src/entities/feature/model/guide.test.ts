import { describe, expect, it } from 'vitest';

import { guideTolerance, guideValues, type GuideUse } from './guide';

const use = (extra: Partial<GuideUse>): GuideUse => ({
  intent: 'x',
  op: 'gte',
  value: 1,
  mode: 'soft',
  tolerance: null,
  onMiss: null,
  note: '',
  ...extra,
});

describe('a guide use', () => {
  it('reads its tolerance as a number, a share of the threshold, or none', () => {
    expect(guideTolerance(use({ tolerance: 5 }))).toBe(5);
    expect(guideTolerance(use({ tolerance: { relative: 0.2 } }))).toEqual({ relative: 0.2 });
    expect(guideTolerance(use({ tolerance: null }))).toBeUndefined();
    expect(guideTolerance(use({ tolerance: { absolute: 1 } }))).toBeUndefined();
  });

  it('reads its values as a list', () => {
    expect(guideValues(use({ value: 30 }))).toEqual([30]);
    expect(guideValues(use({ op: 'between', value: [2, 10] }))).toEqual([2, 10]);
    expect(guideValues(use({ op: 'in', value: ['A', 'B'] }))).toEqual(['A', 'B']);
    expect(guideValues(use({ op: 'not_null', value: null }))).toEqual([]);
  });
});
