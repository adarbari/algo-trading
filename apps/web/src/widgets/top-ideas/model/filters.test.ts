import { describe, expect, it } from 'vitest';

import { IDEA_FACTS, type Idea, type IdeaPick } from '@/entities/idea';

import { filterIdeas, filterOptions, optionLabel } from './filters';

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
  unknown:
    n === null
      ? {
          code: 'NULL' as const,
          kind: 'NOT_STORED' as const,
          guideTerm: 'unavailable_not_stored',
          kindText: 'not available for this instrument',
          cause: null,
        }
      : null,
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

const withBits = (base: Idea, bits: Partial<Idea>): Idea => ({ ...base, ...bits });
const risky = withBits(idea('D', 'QUALIFIED', 40), {
  watchOut: [{ id: 'liquidity_risk', label: 'Liquidity risk' }],
  regime: 'CLOUDS',
  picks: [{ ...pick('QUALIFIED'), screenerId: 'liq', screenerName: 'Liquidity' }],
});
const ideas = [
  idea('A', 'QUALIFIED', 30),
  idea('B', 'WATCH', 3),
  idea('C', 'QUALIFIED', null),
  risky,
];
const symbols = (kept: Idea[]) => kept.map((i) => i.symbol);

describe('filterIdeas', () => {
  it('keeps everything with no view and no filter', () => {
    expect(filterIdeas(ideas, {})).toHaveLength(4);
  });

  it('High conviction keeps the qualified ideas', () => {
    expect(symbols(filterIdeas(ideas, { view: 'conviction' }))).toEqual(['A', 'C', 'D']);
  });

  it('No earnings soon hides earnings within 14 sessions, keeping unknown dates', () => {
    expect(symbols(filterIdeas(ideas, { view: 'no-earnings' }))).toEqual(['A', 'C', 'D']);
  });

  it('filters by screener, decision, liquidity and regime, together with the view', () => {
    expect(symbols(filterIdeas(ideas, { screener: 'liq' }))).toEqual(['D']);
    expect(symbols(filterIdeas(ideas, { decision: 'WATCH' }))).toEqual(['B']);
    expect(symbols(filterIdeas(ideas, { liq: 'risk' }))).toEqual(['D']);
    expect(symbols(filterIdeas(ideas, { liq: 'ok' }))).toEqual(['A', 'B', 'C']);
    expect(symbols(filterIdeas(ideas, { regime: 'CLOUDS' }))).toEqual(['D']);
    expect(symbols(filterIdeas(ideas, { view: 'conviction', decision: 'WATCH' }))).toEqual([]);
  });
});

describe('filterOptions', () => {
  it('offers only the values some idea has, labelled', () => {
    expect(filterOptions(ideas, 'screener')).toEqual([
      { value: 's', label: 'S' },
      { value: 'liq', label: 'Liquidity' },
    ]);
    expect(filterOptions(ideas, 'decision').map((o) => o.value)).toEqual(['QUALIFIED', 'WATCH']);
    expect(filterOptions(ideas, 'regime')).toEqual([{ value: 'CLOUDS', label: 'CLOUDS' }]);
    expect(filterOptions(ideas, 'liq').map((o) => o.label)).toEqual([
      'No liquidity risk',
      'Liquidity risk',
    ]);
    expect(optionLabel(ideas, 'screener', 'liq')).toBe('Liquidity');
    expect(optionLabel(ideas, 'screener', 'gone')).toBe('gone');
  });
});
