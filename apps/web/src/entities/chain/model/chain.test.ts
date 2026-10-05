import { describe, expect, it } from 'vitest';

import {
  chainRows,
  defaultExpiry,
  expiryLabel,
  inDeltaBand,
  plainEnglish,
  upcomingExpiries,
  type OptionChain,
  type OptionQuote,
} from './chain';

const quote = (patch: Partial<OptionQuote>): OptionQuote => ({
  instrumentId: 'OPT:X',
  expiry: '2026-11-20',
  right: 'P',
  strike: 300,
  bid: 2.42,
  ask: 2.61,
  last: 2.5,
  volume: 10,
  openInterest: 19780,
  iv: 0.3,
  delta: -0.12,
  gamma: 0.004,
  theta: -0.05,
  vega: 0.3,
  ...patch,
});

const chain: OptionChain = {
  underlyingId: 'EQ:A',
  session: '2026-10-02',
  status: 'OK',
  expiries: [
    { date: '2026-09-25', days: -7 },
    { date: '2026-10-02', days: 0 },
    { date: '2026-10-09', days: 7 },
    { date: '2026-10-23', days: 21 },
    { date: '2026-11-20', days: 49 },
  ],
  strikes: [100, 300, 330, 340],
};

const quotes = [
  quote({ instrumentId: 'P100', strike: 100, bid: 0, delta: -0.001 }),
  quote({ instrumentId: 'P300', strike: 300 }),
  quote({ instrumentId: 'C340', right: 'C', strike: 340, delta: 0.4, bid: 5 }),
  quote({ instrumentId: 'P340', strike: 340, delta: -0.6, bid: 9 }),
  quote({ instrumentId: 'P300-oct', strike: 300, expiry: '2026-10-23' }),
];

const options = { expiry: '2026-11-20', symbol: 'AAPL', spot: 333.6 } as const;

describe('option chain', () => {
  it('highlights |delta| from 0.08 to 0.15', () => {
    expect(inDeltaBand(-0.08)).toBe(true);
    expect(inDeltaBand(0.15)).toBe(true);
    expect(inDeltaBand(-0.16)).toBe(false);
    expect(inDeltaBand(null)).toBe(false);
  });

  it('keeps one expiry and right, near the money unless asked for all strikes', () => {
    const near = chainRows(quotes, { ...options, right: 'P', nearMoney: true });
    expect(near.map((r) => [r.id, r.inBand])).toEqual([
      ['P300', true],
      ['P340', false],
    ]);
    const all = chainRows(quotes, { ...options, right: 'P', nearMoney: false });
    expect(all.map((r) => r.id)).toEqual(['P100', 'P300', 'P340']);
    const calls = chainRows(quotes, { ...options, right: 'C', nearMoney: true });
    expect(calls.map((r) => r.id)).toEqual(['C340']);
    const unknownSpot = chainRows(quotes, { ...options, spot: null, right: 'P', nearMoney: true });
    expect(unknownSpot.map((r) => r.id)).toEqual(['P100', 'P300', 'P340']);
  });

  it('says what each contract means in plain English', () => {
    expect(plainEnglish('P', { strike: 300, bid: 2.42 }, 333.6, 'AAPL', '2026-11-20')).toBe(
      'Get paid $242 now; buy 100 AAPL at $300 if it falls ~10% by 20 Nov',
    );
    expect(plainEnglish('C', { strike: 340, bid: 5 }, 333.6, 'AAPL', '2026-11-20')).toBe(
      'Get paid $500 now; sell 100 AAPL at $340 if it rises ~2% by 20 Nov',
    );
    expect(plainEnglish('P', { strike: 340, bid: 9 }, 333.6, 'AAPL', '2026-11-20')).toBe(
      'AAPL is already below $340: expect to buy 100 at $340',
    );
    expect(plainEnglish('P', { strike: 100, bid: 0 }, 333.6, 'AAPL', '2026-11-20')).toBe(
      'No bid: nobody pays for this put today',
    );
    expect(plainEnglish('P', { strike: 297.5, bid: 1 }, null, 'AAPL', '2026-11-20')).toBe(
      'Get paid $100 now for this put',
    );
  });

  it("opens on the first expiry three weeks out by the server's days, labelled with them", () => {
    expect(defaultExpiry(chain)).toBe('2026-10-23');
    const one = { ...chain, expiries: [{ date: '2026-10-05', days: 3 }] };
    expect(defaultExpiry(one)).toBe('2026-10-05');
    expect(defaultExpiry({ ...chain, expiries: [] })).toBeNull();
    expect(expiryLabel({ date: '2026-11-20', days: 49 })).toBe('20 Nov · 49d');
    expect(upcomingExpiries(chain).map((e) => e.date)[0]).toBe('2026-10-02');
  });
});
