import { describe, expect, it } from 'vitest';

import { IDEA_FACTS } from './facts';
import { earningsBeforeExpiry, factOf, NO_IDEAS, toIdeasData, type IdeasResponse } from './idea';

type Served = NonNullable<IdeasResponse['ideas']>;
type Item = Served['items'][number];
type Best = Item['best'];
type By = Item['pickedBy'][number];

const best = (configId: string, decision: string, score: number | null): Best => ({
  configId,
  decision,
  score,
  reasons: '',
  criteria: [],
});

const by = (configId: string, position: number, decision = 'QUALIFIED', own = false): By => ({
  configId,
  own,
  position,
  score: 1 / position,
  decision,
});

const value = (name: string, v: unknown) => ({
  name,
  value: v,
  unknown: null,
  info: { format: 'DATE' as const, unit: null, dtype: 'date', nullMeaning: '' },
});

const item = (
  rank: number,
  symbol: string | null,
  served: Best,
  pickedBy: By[],
  facts = [value('x', 1)],
  extra: Partial<Item> = {},
): Item => ({
  rank,
  instrumentId: `id-${String(rank)}`,
  score: 1 / rank,
  regime: rank === 1 ? 'STRESS' : null,
  sizeMultiplier: rank === 1 ? 0.5 : null,
  watchOut: [],
  instrument: symbol === null ? null : { symbol, name: `${symbol} Inc`, features: facts },
  best: served,
  pickedBy,
  metrics: [],
  ...extra,
});

const screener = (id: string, name: string, notRun = false): Served['screeners'][number] => ({
  screener: { id, name, owner: 'abhinav', version: 3 },
  run: notRun ? null : { runId: `run-${id}`, configVersion: 2, paused: id === 'vrp' ? 1 : 0 },
  notRun: notRun
    ? {
        code: 'NOT_RUN',
        kind: 'NOT_RUN',
        guideTerm: 'not_run',
        kindText: 'not run for this session',
        reason: null,
        cause: null,
      }
    : null,
  picked: notRun ? 0 : 7,
  withheld: id === 'hidden',
  top: notRun ? [] : [{ instrumentId: 'id-1', score: 84, instrument: { symbol: 'AAPL' } }],
});

const response: IdeasResponse = {
  ideas: {
    session: '2026-10-02',
    total: 3,
    hasMore: false,
    nextCursor: null,
    facets: null,
    pausedTotal: 1,
    paused: [
      {
        instrumentId: 'id-9',
        instrument: { symbol: 'XOM' },
        result: {
          configId: 'vrp',
          score: 70,
          reasons: 'regime=STRESS: vrp pauses in STRESS',
          regime: 'STRESS',
        },
      },
    ],
    screeners: [
      screener('vrp', 'VRP scanner'),
      screener('liq', 'liq'),
      screener('gone', 'Gone', true),
    ],
    items: [
      item(
        1,
        'AAPL',
        best('liq', 'QUALIFIED', 84),
        [by('liq', 1), by('vrp', 2, 'WATCH', true)],
        [
          value(IDEA_FACTS.nextEarnings, '2026-10-29'),
          value(IDEA_FACTS.earningsBeforeExpiry, true),
        ],
      ),
      item(2, null, best('liq', 'EVENT_RISK', null), [by('liq', 1, 'EVENT_RISK')]),
    ],
  },
};

describe('toIdeasData', () => {
  const data = toIdeasData(response);

  it('serves each idea from the best pick the server chose, in the server order', () => {
    const [first] = data.ideas;
    expect(first?.pickedBy.map((p) => [p.screenerId, p.screenerName, p.position, p.own])).toEqual([
      ['liq', 'liq', 1, false],
      ['vrp', 'VRP scanner', 2, true],
    ]);
    expect(first?.best).toMatchObject({ screenerId: 'liq', decision: 'QUALIFIED', score: 84 });
    expect(first?.score).toBe(1);
    expect(first && factOf(first, IDEA_FACTS.nextEarnings)?.value).toBe('2026-10-29');
    expect(first && earningsBeforeExpiry(first)).toBe(true);
  });

  it('keeps an instrument the snapshot lacks', () => {
    expect(data.ideas.map((i) => i.instrumentId)).toEqual(['id-1', 'id-2']);
    const second = data.ideas[1];
    expect(second?.symbol).toBeNull();
    expect(second && earningsBeforeExpiry(second)).toBe(false);
  });

  it('lists the screeners as served, with the run counts and why one did not run', () => {
    expect(data.screeners.map((s) => [s.id, s.withheld])).toEqual([
      ['vrp', false],
      ['liq', false],
      ['gone', false],
    ]);
    expect(data.screeners[0]).toMatchObject({
      picked: 7,
      notRun: null,
      version: 2,
      top: [{ symbol: 'AAPL', score: 84 }],
    });
    expect(data.screeners[2]).toMatchObject({
      picked: 0,
      notRun: { kind: 'NOT_RUN', guideTerm: 'not_run', kindText: 'not run for this session' },
      version: 3,
      top: [],
    });
  });

  it("carries each idea's regime stamp, as stored (null: not stamped)", () => {
    expect(data.ideas.map((i) => [i.regime, i.sizeMultiplier])).toEqual([
      ['STRESS', 0.5],
      [null, null],
    ]);
  });

  it('lists the paused picks apart, with the screener name and the stored reason', () => {
    expect(data.pausedTotal).toBe(1);
    expect(data.paused).toEqual([
      {
        instrumentId: 'id-9',
        symbol: 'XOM',
        screenerId: 'vrp',
        screenerName: 'VRP scanner',
        score: 70,
        reason: 'regime=STRESS: vrp pauses in STRESS',
        regime: 'STRESS',
      },
    ]);
  });

  it('reads nothing stored as no ideas', () => {
    expect(toIdeasData({ ideas: null })).toEqual(NO_IDEAS);
  });
});

describe('display values and watch-outs', () => {
  const rich: IdeasResponse = {
    ideas: {
      ...(response.ideas as Served),
      items: [
        item(
          1,
          'AAPL',
          best('liq', 'LIQUIDITY_RISK', 60),
          [by('liq', 1, 'LIQUIDITY_RISK'), by('vrp', 3)],
          [value(IDEA_FACTS.earningsBeforeExpiry, true)],
          {
            watchOut: ['leveraged_inverse', 'large_move', 'liquidity_risk', 'odd_flag'],
            metrics: [
              { name: 'iv30', value: 0.3 },
              { name: 'hv30', value: 0.2 },
              { name: 'note', value: 'x' },
            ],
          },
        ),
      ],
    },
  };
  const [idea] = toIdeasData(rich).ideas;

  it("takes the best pick's served display values as they are", () => {
    expect(idea?.metrics).toEqual({ iv30: 0.3, hv30: 0.2, note: 'x' });
  });

  it('labels the served watch-outs, each once, and adds none of its own', () => {
    expect(idea?.watchOut.map((w) => w.label)).toEqual([
      'Leveraged / inverse',
      'Large move',
      'Liquidity risk',
      'Odd flag',
    ]);
  });

  it('names the screeners', () => {
    expect(idea?.pickedBy.map((p) => p.screenerName)).toEqual(['liq', 'VRP scanner']);
  });
});
