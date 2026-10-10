import { describe, expect, it } from 'vitest';

import { blankDraft } from './draft';
import { summaryOf } from './summary';

describe('summaryOf', () => {
  it('says each choice of the draft in one line', () => {
    const lines = summaryOf({
      ...blankDraft(),
      screeners: ['a', 'b'],
      schedule: 'on_event',
      event: 'earnings_reaction',
      topK: 10,
      horizons: [60, 20],
      universe: 'liquid',
      baselines: ['size_small'],
      frozenFrom: '2026-04-01',
    });
    expect(Object.fromEntries(lines.map((l) => [l.label, l.value]))).toEqual({
      Screens: 'a, b',
      Picks: 'After earnings are reported · top 10',
      Trade: 'enter 1 session(s) after · hold 20 / 60 days · 15 bps · win = beats SPY',
      Compare: 'liquid · against size_small',
      'Out-of-sample': 'from 2026-04-01',
    });
  });

  it('says what is missing', () => {
    const lines = summaryOf({ ...blankDraft(), take: 'all', win: 'other', costBps: null });
    expect(lines[0]?.value).toBe('none chosen');
    expect(lines[1]?.value).toBe('Every session · all that qualify');
    expect(lines[4]?.value).toBe('none');
  });
});
