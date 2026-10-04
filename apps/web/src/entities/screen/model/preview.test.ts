import { describe, expect, it } from 'vitest';

import {
  decisionCounts,
  extraColumns,
  narrowMissGroups,
  type NarrowMiss,
  type PreviewRow,
  type ScreenPreview,
} from './preview';

describe('decisionCounts', () => {
  it('orders the decisions and omits empty ones', () => {
    const preview = {
      decisions: { REJECT: 5, QUALIFIED: 2, WATCH: 0, SKIPPED: 1, CUSTOM: 3 },
    } as unknown as ScreenPreview;
    expect(decisionCounts(preview)).toEqual([
      { decision: 'QUALIFIED', count: 2 },
      { decision: 'REJECT', count: 5 },
      { decision: 'SKIPPED', count: 1 },
      { decision: 'CUSTOM', count: 3 },
    ]);
  });
});

describe('extraColumns', () => {
  it('lists the stored columns in first-seen order', () => {
    const rows = [{ columns: { a: 1 } }, { columns: { b: 2, a: 3 } }] as unknown as PreviewRow[];
    expect(extraColumns(rows)).toEqual(['a', 'b']);
  });
});

describe('narrowMissGroups', () => {
  it('groups by criterion, biggest first', () => {
    const miss = (criterion_id: string): NarrowMiss => ({
      instrument_id: 'EQ:1',
      criterion_id,
      field: 'f',
      value: 1,
      threshold: 2,
      distance: 1,
      normalised: 0.5,
    });
    const groups = narrowMissGroups([miss('a'), miss('b'), miss('b')]);
    expect(groups.map((g) => [g.criterionId, g.misses.length])).toEqual([
      ['b', 2],
      ['a', 1],
    ]);
  });
});
