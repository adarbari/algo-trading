import { describe, expect, it } from 'vitest';

import { pendingLine } from './pending';

const formula = (criterion: Record<string, unknown> | null) =>
  ({ name: 'draft_near_high', criterion }) as Parameters<typeof pendingLine>[0];

describe('pendingLine', () => {
  it('names the field and the operator with its threshold', () => {
    expect(
      pendingLine(formula({ field: 'feature.draft_near_high', op: 'gte', value: -0.05 })),
    ).toEqual({ name: 'feature.draft_near_high', summary: '≥ -0.05' });
  });

  it('joins a range and has no threshold for an op that takes none', () => {
    expect(
      pendingLine(formula({ field: 'feature.x', op: 'between', value: [1, 2] }))?.summary,
    ).toMatch(/1 and 2$/);
    expect(pendingLine(formula({ field: 'feature.x', op: 'not_null' }))?.summary).not.toMatch(
      /undefined/,
    );
  });

  it('is nothing for a formula with no criterion', () => {
    expect(pendingLine(formula(null))).toBeNull();
  });
});
