import { describe, expect, it } from 'vitest';

import { IDEA_FACTS } from './facts';
import { earningsBeforeExpiry, factOf, NO_IDEAS, toIdeasData, type IdeasResponse } from './idea';

type Served = NonNullable<IdeasResponse['ideas']>;
type Item = Served['items'][number];
type Pick = Item['picks'][number];

const pick = (configId: string, decision: string, score: number | null): Pick => ({
  configId,
  decision,
  score,
  reasons: '',
  flags: [],
  criteria: [],
  columns: [],
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
  picks: Pick[],
  facts = [value('x', 1)],
): Item => ({
  rank,
  instrumentId: `id-${String(rank)}`,
  regime: rank === 1 ? 'STRESS' : null,
  sizeMultiplier: rank === 1 ? 0.5 : null,
  instrument: symbol === null ? null : { symbol, features: facts },
  picks,
});

const screener = (id: string, name: string, notRun = false): Served['screeners'][number] => ({
  screener: { id, name, owner: 'abhinav', version: 3 },
  run: notRun ? null : { runId: `run-${id}`, configVersion: 2, paused: id === 'vrp' ? 1 : 0 },
  notRun: notRun
    ? { code: 'NOT_RUN', kind: 'NOT_RUN', guideTerm: 'not_run', reason: null, cause: null }
    : null,
  picked: notRun ? 0 : 7,
  top: notRun ? [] : [{ instrumentId: 'id-1', score: 84, instrument: { symbol: 'AAPL' } }],
});

const response: IdeasResponse = {
  ideas: {
    session: '2026-10-02',
    priority: ['vrp', 'liq'],
    total: 3,
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
        [pick('vrp', 'WATCH', 60), pick('liq', 'QUALIFIED', 84)],
        [
          value(IDEA_FACTS.nextEarnings, '2026-10-29'),
          value(IDEA_FACTS.earningsBeforeExpiry, true),
        ],
      ),
      item(2, null, [pick('liq', 'EVENT_RISK', null)]),
      item(3, 'ZZZ', []),
    ],
  },
};

describe('toIdeasData', () => {
  const data = toIdeasData(response);

  it('keeps the server order of picks and takes the best decision', () => {
    const [first] = data.ideas;
    expect(first?.picks.map((p) => p.screenerId)).toEqual(['vrp', 'liq']);
    expect(first?.best).toMatchObject({ screenerId: 'liq', decision: 'QUALIFIED', score: 84 });
    expect(first && factOf(first, IDEA_FACTS.nextEarnings)?.value).toBe('2026-10-29');
    expect(first && earningsBeforeExpiry(first)).toBe(true);
  });

  it('keeps an instrument the snapshot lacks and drops an idea nobody picked', () => {
    expect(data.ideas.map((i) => i.instrumentId)).toEqual(['id-1', 'id-2']);
    const second = data.ideas[1];
    expect(second?.symbol).toBeNull();
    expect(second && earningsBeforeExpiry(second)).toBe(false);
  });

  it('lists the screeners as served, with the run counts and why one did not run', () => {
    expect(data.screeners.map((s) => s.id)).toEqual(['vrp', 'liq', 'gone']);
    expect(data.screeners[0]).toMatchObject({
      picked: 7,
      notRun: null,
      version: 2,
      top: [{ symbol: 'AAPL', score: 84 }],
    });
    expect(data.screeners[2]).toMatchObject({
      picked: 0,
      notRun: { kind: 'NOT_RUN', guideTerm: 'not_run' },
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
          [
            {
              ...pick('liq', 'LIQUIDITY_RISK', 60),
              flags: ['leveraged_inverse', 'large_move'],
              columns: [
                { name: 'iv30', value: 0.3 },
                { name: 'hv30', value: 0.2 },
              ],
              criteria: [
                { id: 'iv30', value: 0.99 },
                { id: 'adv', value: 4.5e7 },
              ],
            },
            {
              ...pick('vrp', 'QUALIFIED', 84),
              flags: ['large_move', 'odd_flag'],
              columns: [
                { name: 'iv30', value: 0.31 },
                { name: 'put_roc', value: 0.019 },
                { name: 'note', value: 'x' },
              ],
            },
          ],
          [value(IDEA_FACTS.earningsBeforeExpiry, true)],
        ),
      ],
    },
  };
  const [idea] = toIdeasData(rich).ideas;

  it('takes each value from the best pick that has it, columns before criterion values', () => {
    expect(idea?.metrics).toEqual({
      iv30: 0.31,
      put_roc: 0.019,
      note: 'x',
      hv30: 0.2,
      adv: 4.5e7,
    });
  });

  it('lists each watch-out once, with the served earnings-before-expiry flag', () => {
    expect(idea?.watchOut.map((w) => w.label)).toEqual([
      'Leveraged / inverse',
      'Large move',
      'Liquidity risk',
      'Odd flag',
      'Earnings before expiry',
    ]);
  });

  it('names the screeners', () => {
    expect(idea?.picks.map((p) => p.screenerName)).toEqual(['liq', 'VRP scanner']);
  });
});
