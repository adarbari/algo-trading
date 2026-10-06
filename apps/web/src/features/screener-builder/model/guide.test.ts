import { describe, expect, it } from 'vitest';

import type { CatalogueFeature, GuideUse } from '@/entities/feature';
import type { Criterion } from '@/entities/screen';

import { applyGuideUse, guideCriterionText, guideModeText } from './guide';

const use = (extra: Partial<GuideUse>): GuideUse => ({
  intent: 'x',
  op: 'gte',
  value: 0.1,
  mode: 'soft',
  tolerance: 0.03,
  onMiss: null,
  note: '',
  ...extra,
});
const feature = (dtype: string, unit: string | null): CatalogueFeature =>
  ({ dtype, unit, categories: [] }) as unknown as CatalogueFeature;
const CRITERION: Criterion = {
  id: 'ret',
  field: 'rollup.price_stats@v2.ret_20d',
  op: 'gt',
  mode: 'hard',
  value: 0,
};

describe('applyGuideUse', () => {
  it('sets the operator, value, mode, tolerance and on_miss, keeping the id and field', () => {
    expect(applyGuideUse(CRITERION, use({ onMiss: 'LIQUIDITY_RISK' }))).toEqual({
      ...CRITERION,
      op: 'gte',
      value: 0.1,
      mode: 'soft',
      tolerance: 0.03,
      on_miss: 'LIQUIDITY_RISK',
    });
  });

  it('a hard use carries no tolerance, a score no on_miss, a null check no value', () => {
    expect(
      applyGuideUse(CRITERION, use({ mode: 'hard', tolerance: null, value: 0 })),
    ).toMatchObject({
      op: 'gte',
      value: 0,
      mode: 'hard',
      tolerance: undefined,
      on_miss: undefined,
    });
    expect(
      applyGuideUse(CRITERION, use({ mode: 'score', tolerance: 20, onMiss: 'WATCH' })),
    ).toMatchObject({
      mode: 'score',
      tolerance: 20,
      on_miss: undefined,
    });
    expect(
      applyGuideUse(CRITERION, use({ op: 'not_null', value: null, mode: 'hard', tolerance: null })),
    ).toMatchObject({
      op: 'not_null',
      value: undefined,
    });
    expect(applyGuideUse(CRITERION, use({ mode: 'maybe' })).mode).toBe('hard');
  });
});

describe('a guided criterion in words', () => {
  it("formats the value in the field's unit", () => {
    expect(guideCriterionText(use({}), feature('float', 'decimal'))).toBe('≥ 10.0%');
    expect(guideCriterionText(use({ op: 'lt', value: 30 }), feature('float32', 'pct_points'))).toBe(
      '< 30',
    );
    expect(
      guideCriterionText(use({ op: 'between', value: [2e9, 1e10] }), feature('float', 'usd')),
    ).toMatch(/^between \$2.*and \$10/);
    expect(
      guideCriterionText(use({ op: 'in', value: ['A', 'B'] }), feature('str', 'category')),
    ).toBe('in A, B');
    expect(guideCriterionText(use({ op: 'eq', value: true }), feature('bool', 'flag'))).toBe(
      '= true',
    );
    expect(guideCriterionText(use({ op: 'not_null', value: null }), feature('float', null))).toBe(
      'has a value',
    );
  });

  it('says the mode with its near-miss band', () => {
    expect(guideModeText(use({}), feature('float', 'decimal'))).toBe(
      'soft, a near miss within 3.0%',
    );
    expect(
      guideModeText(
        use({ tolerance: { relative: 0.2 }, onMiss: 'LIQUIDITY_RISK' }),
        feature('float', 'usd'),
      ),
    ).toBe('soft, a near miss within 20% of the threshold (LIQUIDITY_RISK)');
    expect(guideModeText(use({ mode: 'hard', tolerance: null }), feature('float', null))).toBe(
      'hard',
    );
    expect(
      guideModeText(use({ mode: 'score', tolerance: 20 }), feature('float', 'pct_points')),
    ).toBe('score, a near miss within 20');
  });
});
