import { describe, expect, it } from 'vitest';

import { EDGES_FIXTURE } from './fixtures';
import { statusLabel, statusTone, toEdges } from './edges';

describe('toEdges', () => {
  const [momentum, rejected] = toEdges(EDGES_FIXTURE);

  it('keeps only the frozen, non-exploratory rows of the canonical run, screeners first', () => {
    expect(momentum?.frozenRows.map((r) => [r.variant, r.role, r.hitRate])).toEqual([
      ['momentum_12_1', 'screener', 0.58],
      ['equal_weight', 'baseline', 0.51],
    ]);
  });

  it('has no rows for an edge without a canonical run', () => {
    expect(rejected?.frozenRows).toEqual([]);
  });
});

describe('status words', () => {
  it('capitalises the status and gives each a tone', () => {
    expect(statusLabel('candidate')).toBe('Candidate');
    expect(statusTone('evidenced')).toBe('positive');
    expect(statusTone('rejected')).toBe('negative');
    expect(statusTone('anything else')).toBe('neutral');
  });
});
