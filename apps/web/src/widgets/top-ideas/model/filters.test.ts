import { describe, expect, it } from 'vitest';

import type { Idea, IdeaPick } from '@/entities/idea';

import { decisionsPresent, filterIdeas, NO_FILTERS } from './filters';

const pick = (decision: string): IdeaPick => ({
  screenerId: 's',
  user: 'u',
  version: 1,
  decision,
  score: 1,
  tier: null,
  klass: null,
  reasons: '',
});
const idea = (symbol: string, decision: string, days: number | null): Idea => ({
  instrumentId: `EQ:${symbol}`,
  symbol,
  rank: 1,
  picks: [pick(decision)],
  best: pick(decision),
  nextEarningsDate: null,
  daysToEarnings: days,
  closestExpiryDte: null,
  earningsBeforeExpiry: false,
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

  it('hides earnings within 14 days, keeping unknown dates', () => {
    const kept = filterIdeas(ideas, { ...NO_FILTERS, hideEarningsSoon: true });
    expect(kept.map((i) => i.symbol)).toEqual(['A', 'C']);
  });

  it('lists the decisions present once each', () => {
    expect(decisionsPresent(ideas)).toEqual(['QUALIFIED', 'WATCH']);
  });
});
