import { describe, expect, it } from 'vitest';

import { IDEA_FACTS, type Idea, type IdeaPick } from '@/entities/idea';

import { decisionsPresent, EARNINGS_SOON_LABEL, filterIdeas, NO_FILTERS } from './filters';

const pick = (decision: string): IdeaPick => ({
  screenerId: 's',
  screenerName: 'S',
  flags: [],
  columns: {},
  criterionValues: {},
  decision,
  score: 1,
  reasons: '',
});
const sessions = (n: number | null) => ({
  name: IDEA_FACTS.sessionsToEarnings,
  value: n,
  unknown: n === null ? { code: 'NULL' as const, detail: 'no report date' } : null,
  info: { format: 'NUMBER' as const },
});
const idea = (symbol: string, decision: string, days: number | null): Idea => ({
  instrumentId: `id-${symbol}`,
  symbol,
  rank: 1,
  picks: [pick(decision)],
  best: pick(decision),
  regime: null,
  sizeMultiplier: null,
  facts: { [IDEA_FACTS.sessionsToEarnings]: sessions(days) },
  metrics: {},
  watchOut: [],
});

const ideas = [idea('A', 'QUALIFIED', 30), idea('B', 'WATCH', 3), idea('C', 'QUALIFIED', null)];

describe('filterIdeas', () => {
  it('keeps everything with no filters', () => {
    expect(filterIdeas(ideas, NO_FILTERS)).toHaveLength(3);
  });

  it('filters by decision', () => {
    const kept = filterIdeas(ideas, { ...NO_FILTERS, decisions: ['WATCH'] });
    expect(kept.map((i) => i.symbol)).toEqual(['B']);
  });

  it('hides earnings within 14 sessions, keeping unknown dates', () => {
    const kept = filterIdeas(ideas, { ...NO_FILTERS, hideEarningsSoon: true });
    expect(kept.map((i) => i.symbol)).toEqual(['A', 'C']);
    expect(EARNINGS_SOON_LABEL).toBe('Hide earnings within 14 sessions');
  });

  it('lists the decisions present once each', () => {
    expect(decisionsPresent(ideas)).toEqual(['QUALIFIED', 'WATCH']);
  });
});
