import { describe, expect, it } from 'vitest';

import type { PreviewRow } from './preview';
import { scoreBreakdown } from './score';

type Criterion = PreviewRow['criteria'][number];

const c = (id: string, outcome: string, penalty: number, extra: Partial<Criterion> = {}) => ({
  criterion_id: id,
  field: `feature.${id}`,
  mode: 'soft',
  value: 1,
  outcome,
  distance: null,
  normalised: null,
  penalty,
  ...extra,
});

const row = (score: number | null, criteria: Criterion[]): PreviewRow => ({
  instrument_id: 'EQ:AAA',
  symbol: 'AAA',
  rank: 1,
  decision: 'WATCH',
  score,
  flags: [],
  reasons: [],
  columns: {},
  criteria,
});

describe('scoreBreakdown', () => {
  it('lists each penalty worst first with why, and counts the passes', () => {
    const got = scoreBreakdown(
      row(86, [
        c('price', 'PASS', 0),
        c('spread', 'NEAR', 4, { normalised: 0.4 }),
        c('iv_rank', 'MISSING', 10),
      ]),
    );
    expect(got.lines.map((l) => [l.criterionId, l.penalty, l.why])).toEqual([
      ['iv_rank', 10, 'no value'],
      ['spread', 4, 'near miss, 40% into the tolerance'],
    ]);
    expect(got).toMatchObject({ score: 86, penalties: 14, clipped: false, passed: 1 });
  });

  it('says why each kind of miss cost points, and flags a score clipped at 0', () => {
    const got = scoreBreakdown(
      row(0, [
        c('oi', 'FAIL', 100, { mode: 'hard' }),
        c('trend', 'FAIL', 10, { mode: 'score' }),
        c('skew', 'FAIL', 100),
        c('near', 'NEAR', 10),
      ]),
    );
    expect(got.lines.map((l) => l.why)).toEqual([
      'failed a hard criterion',
      'missed beyond the tolerance',
      'missed (a score criterion only costs points)',
      'near miss',
    ]);
    expect(got.clipped).toBe(true);
  });
});
