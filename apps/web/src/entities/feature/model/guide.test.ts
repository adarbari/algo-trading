import { describe, expect, it } from 'vitest';

import { guideTolerance, guideValues, ruleText, bandOf, type GuideUse } from './guide';

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

describe('a guide use as a rule and as a band', () => {
  it('writes the rule as the Builder does', () => {
    expect(ruleText(use({ op: 'lte', value: 0.1, tolerance: 0.05 }))).toBe(
      'lte 0.1 soft tolerance 0.05',
    );
    expect(ruleText(use({ op: 'between', value: [2, 10], mode: 'hard' }))).toBe(
      'between 2 10 hard',
    );
    expect(ruleText(use({ op: 'gte', value: 30, tolerance: { relative: 0.2 } }))).toBe(
      'gte 30 soft tolerance 20% of the threshold',
    );
    expect(ruleText(use({ op: 'not_null', value: null, mode: 'hard' }))).toBe('not_null hard');
  });

  it('turns a numeric rule into the span of values it passes', () => {
    expect(bandOf(use({ op: 'gte', value: 1 }))).toEqual({ from: 1 });
    expect(bandOf(use({ op: 'gt', value: 1 }))).toEqual({ from: 1 });
    expect(bandOf(use({ op: 'lte', value: 0.1 }))).toEqual({ to: 0.1 });
    expect(bandOf(use({ op: 'between', value: [2, 10] }))).toEqual({ from: 2, to: 10 });
  });

  it('has no band for a rule that is not a span of numbers', () => {
    expect(bandOf(use({ op: 'eq', value: 'UPTREND' }))).toBeNull();
    expect(bandOf(use({ op: 'in', value: ['A', 'B'] }))).toBeNull();
    expect(bandOf(use({ op: 'between', value: [2] }))).toBeNull();
    expect(bandOf(use({ op: 'gte', value: 'x' }))).toBeNull();
  });
});
