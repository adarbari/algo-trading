import { describe, expect, it } from 'vitest';

import { decisionLabel, decisionTone, toIdeasData, type IdeasResponse } from './idea';

const pick = (config_id: string, decision: string, score: number | null) => ({
  config_id,
  config_version: 2,
  user: 'abhinav',
  session: '2026-10-02',
  decision,
  score,
  tier: 'A',
  klass: 'B',
  reasons: '',
  criteria: [],
  columns: {},
  criterion_values: {},
  flags: [],
});

const response: IdeasResponse = {
  session: '2026-10-02',
  priority: ['vrp', 'liq', 'unused'],
  total: 3,
  screeners: [
    { config_id: 'vrp', user: 'abhinav', name: 'VRP scanner', version: 2 },
    { config_id: 'liq', user: 'abhinav', name: 'liq', version: 2 },
    { config_id: 'unused', user: null, name: 'Unused one', version: null },
  ],
  items: [
    {
      rank: 1,
      instrument_id: 'EQ:A',
      symbol: 'AAPL',
      picks: [pick('liq', 'WATCH', 60), pick('vrp', 'QUALIFIED', 84), pick('new', 'WATCH', 10)],
      next_earnings_date: '2026-10-29',
      days_to_earnings: 27,
      closest_expiry_dte: 36,
      earnings_before_expiry: true,
    },
    {
      rank: 2,
      instrument_id: 'EQ:M',
      symbol: null,
      picks: [pick('liq', 'EVENT_RISK', null)],
      next_earnings_date: null,
      days_to_earnings: null,
      closest_expiry_dte: null,
      earnings_before_expiry: null,
    },
    {
      rank: 3,
      instrument_id: 'EQ:Z',
      symbol: 'ZZZ',
      picks: [],
      next_earnings_date: null,
      days_to_earnings: null,
      closest_expiry_dte: null,
      earnings_before_expiry: null,
    },
  ],
};

describe('toIdeasData', () => {
  const data = toIdeasData(response);

  it('orders each idea’s picks by priority and takes the best decision', () => {
    const [first] = data.ideas;
    expect(first?.picks.map((p) => p.screenerId)).toEqual(['vrp', 'liq', 'new']);
    expect(first?.best).toMatchObject({ screenerId: 'vrp', decision: 'QUALIFIED', score: 84 });
    expect(first?.earningsBeforeExpiry).toBe(true);
  });

  it('keeps nulls and drops an idea nobody picked', () => {
    expect(data.ideas.map((i) => i.instrumentId)).toEqual(['EQ:A', 'EQ:M']);
    expect(data.ideas[1]).toMatchObject({
      symbol: null,
      closestExpiryDte: null,
      earningsBeforeExpiry: false,
    });
  });

  it('lists screeners in priority order, then any other picker, with counts and top picks', () => {
    expect(data.screeners.map((s) => s.id)).toEqual(['vrp', 'liq', 'unused', 'new']);
    expect(data.screeners[0]).toMatchObject({ qualified: 1, top: [{ symbol: 'AAPL', score: 84 }] });
    expect(data.screeners[1]).toMatchObject({ qualified: 0, user: 'abhinav', version: 2 });
    expect(data.screeners[2]).toMatchObject({ qualified: 0, top: [], version: null });
  });
});

describe('display values and watch-outs', () => {
  const rich: IdeasResponse = {
    ...response,
    items: [
      {
        rank: 1,
        instrument_id: 'EQ:A',
        symbol: 'AAPL',
        next_earnings_date: '2026-10-29',
        days_to_earnings: 27,
        closest_expiry_dte: 36,
        earnings_before_expiry: true,
        picks: [
          {
            ...pick('liq', 'LIQUIDITY_RISK', 60),
            flags: ['leveraged_inverse', 'large_move'],
            columns: { iv30: 0.3, hv30: 0.2 },
            criterion_values: { iv30: 0.99, adv: 4.5e7 },
          },
          {
            ...pick('vrp', 'QUALIFIED', 84),
            flags: ['large_move', 'odd_flag'],
            columns: { iv30: 0.31, put_roc: 0.019, note: 'x' },
          },
        ],
      },
    ],
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

  it('lists each watch-out once, with the earnings-before-expiry flag', () => {
    expect(idea?.watchOut.map((w) => w.label)).toEqual([
      'Large move',
      'Odd flag',
      'Leveraged / inverse',
      'Liquidity risk',
      'Earnings before expiry',
    ]);
  });

  it('names the screeners', () => {
    const data = toIdeasData(rich);
    expect(data.screeners.map((s) => s.name)).toEqual(['VRP scanner', 'liq', 'Unused one']);
    expect(idea?.picks.map((p) => p.screenerName)).toEqual(['VRP scanner', 'liq']);
  });
});

describe('decisions', () => {
  it('labels and tones', () => {
    expect(decisionLabel('EVENT_RISK')).toBe('Event risk');
    expect(decisionTone('QUALIFIED')).toBe('positive');
    expect(decisionTone('WATCH')).toBe('accent');
    expect(decisionTone('EVENT_RISK')).toBe('warning');
    expect(decisionTone('OTHER')).toBe('neutral');
  });
});
