import { describe, expect, it } from 'vitest';

import type { GuideUse } from '@/entities/feature';
import type { Criterion } from '@/entities/screen';

import { applyGuideUse } from './guide';

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
