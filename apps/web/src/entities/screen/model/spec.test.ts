import { describe, expect, it } from 'vitest';

import {
  blankDocument,
  criteriaOf,
  criterionIds,
  criterionOfError,
  isComplete,
  isScreenId,
  newCriterionId,
  previewDocument,
  tieBreakOf,
  toDocument,
  withCriterion,
  withoutCriterion,
  withTieBreak,
  type Criterion,
} from './spec';

const BASE = {
  version: 2,
  criteria: {
    iv30: { field: 'rollup.iv30@v1.iv30', op: 'gte', value: 0.5, mode: 'hard' },
    adv: {
      field: 'rollup.price_stats@v2.adv_usd_20d',
      op: 'gte',
      value: 5e7,
      mode: 'soft',
      tolerance: { relative: 0.2 },
      on_miss: 'LIQUIDITY_RISK',
      label: 'ADV',
    },
  },
};

describe('criteriaOf', () => {
  it('merges the draft over the working copy by id, in order, dropping switched-off ones', () => {
    const draft = {
      id: 'my',
      criteria: {
        iv30: { value: 0.6 },
        adv: { enabled: false },
        close: { field: 'rollup.price_stats@v2.close', op: 'gt', value: 5 },
      },
    };
    const criteria = criteriaOf(BASE, draft);
    expect(criteria.map((c) => c.id)).toEqual(['iv30', 'close']);
    expect(criteria[0]).toMatchObject({ field: 'rollup.iv30@v1.iv30', value: 0.6, mode: 'hard' });
    expect(criteria[1]).toMatchObject({ mode: 'hard', op: 'gt' });
  });

  it('keeps tolerance, miss decision and label', () => {
    expect(criteriaOf(BASE, { id: 'my' })[1]).toMatchObject({
      mode: 'soft',
      tolerance: { relative: 0.2 },
      on_miss: 'LIQUIDITY_RISK',
      label: 'ADV',
    });
  });

  it('reads a draft with nothing resolved', () => {
    expect(criteriaOf(null, blankDocument('x', 'all'))).toEqual([]);
  });
});

describe('editing the document', () => {
  const criterion: Criterion = {
    id: 'iv30',
    field: 'rollup.iv30@v1.iv30',
    op: 'gte',
    mode: 'soft',
    value: 0.4,
    tolerance: 0.1,
  };

  it('sets a criterion as a whole table without undefined keys', () => {
    const next = withCriterion({ id: 'my' }, { ...criterion, on_miss: undefined });
    expect(next.criteria).toEqual({
      iv30: { field: 'rollup.iv30@v1.iv30', op: 'gte', mode: 'soft', value: 0.4, tolerance: 0.1 },
    });
  });

  it('switches an inherited criterion off but drops one the draft added', () => {
    const doc = withCriterion(
      { id: 'my' },
      { id: 'extra', field: 'f', op: 'gt', mode: 'hard', value: 1 },
    );
    expect(withoutCriterion(doc, BASE, 'iv30').criteria).toMatchObject({
      iv30: { enabled: false },
    });
    expect(withoutCriterion(doc, BASE, 'extra').criteria).toEqual({});
  });

  it('lists every id in use, switched off or not', () => {
    expect(criterionIds(BASE, { id: 'my', criteria: { z: { enabled: false } } }).sort()).toEqual([
      'adv',
      'iv30',
      'z',
    ]);
  });

  it('names a new criterion from its field and keeps it unique', () => {
    expect(newCriterionId([], 'rollup.iv30@v1.iv30')).toBe('iv30');
    expect(newCriterionId(['iv30'], 'rollup.iv30@v1.iv30')).toBe('iv30_2');
    expect(newCriterionId([])).toBe('criterion');
  });

  it('sets and reads the tie-break', () => {
    const doc = withTieBreak({ id: 'my' }, 'feature.iv_hv_spread', 'asc');
    expect(tieBreakOf(null, doc)).toEqual({ field: 'feature.iv_hv_spread', order: 'asc' });
    expect(tieBreakOf({ rank: { tie_break: 'a' } }, { id: 'my' })).toEqual({
      field: 'a',
      order: 'desc',
    });
    expect(withTieBreak(doc, null, 'desc')['rank']).toEqual({});
  });
});

describe('isComplete and previewDocument', () => {
  it('needs a field and a threshold (and a tolerance for a soft one)', () => {
    const c: Criterion = { id: 'a', field: 'f', op: 'gte', mode: 'hard' };
    expect(isComplete(c)).toBe(false);
    expect(isComplete({ ...c, value: 1 })).toBe(true);
    expect(isComplete({ ...c, value: 0 })).toBe(true);
    expect(isComplete({ ...c, field: '', value: 1 })).toBe(false);
    expect(isComplete({ ...c, op: 'is_null' })).toBe(true);
    expect(isComplete({ ...c, value: [], op: 'in' })).toBe(false);
    expect(isComplete({ ...c, mode: 'soft', value: 1 })).toBe(false);
    expect(isComplete({ ...c, mode: 'soft', value: 1, tolerance: 0 })).toBe(true);
  });

  it('leaves unfinished criteria out of the preview but keeps switched-off ones', () => {
    const doc = {
      id: 'my',
      criteria: {
        a: { field: 'f', op: 'gt', value: 1 },
        b: { field: '', op: 'gt' },
        c: { enabled: false },
      },
    };
    expect(Object.keys(previewDocument(doc).criteria ?? {})).toEqual(['a', 'c']);
  });
});

describe('documents and ids', () => {
  it('drops the keys the authoring flow manages', () => {
    expect(toDocument({ id: 'x', version: 3, schedule: 'nightly', extends: 'p@1' }, 'my')).toEqual({
      id: 'my',
      extends: 'p@1',
    });
  });

  it('finds the criterion an error names', () => {
    expect(criterionOfError("my.criteria.spread.field: unknown field 'x'")).toBe('spread');
    expect(criterionOfError('my.criteria: needs one')).toBeNull();
    expect(criterionOfError(null)).toBeNull();
  });

  it('checks a screen id like the API', () => {
    expect(isScreenId('my-vrp_2')).toBe(true);
    expect(isScreenId('My')).toBe(false);
    expect(isScreenId('')).toBe(false);
    expect(isScreenId('a'.repeat(65))).toBe(false);
  });
});
