import { describe, expect, it } from 'vitest';

import {
  chainRows,
  defaultExpiry,
  expiryLabel,
  inDeltaBand,
  plainEnglish,
  spotOf,
  type OptionChain,
  type OptionQuote,
} from './chain';

const quote = (patch: Partial<OptionQuote>): OptionQuote => ({
  instrument_id: 'OPT:X',
  expiry: '2026-11-20',
  right: 'P',
  strike: 300,
  bid: 2.42,
  ask: 2.61,
  last: 2.5,
  volume: 10,
  open_interest: 19780,
  iv: 0.3,
  delta: -0.12,
  gamma: 0.004,
  theta: -0.05,
  vega: 0.3,
  rho: -0.1,
  ...patch,
});

const chain: OptionChain = {
  underlying_id: 'EQ:A',
  session: '2026-10-02',
  status: 'OK',
  underlying: { price: 333.6, close: 333.69 },
  our_iv: { iv30: 0.244 },
  expiries: ['2026-10-02', '2026-10-09', '2026-10-23', '2026-11-20'],
  strikes: [100, 300, 330, 340],
  quotes: [
    quote({ instrument_id: 'P100', strike: 100, bid: 0, delta: -0.001 }),
    quote({ instrument_id: 'P300', strike: 300 }),
    quote({ instrument_id: 'C340', right: 'C', strike: 340, delta: 0.4, bid: 5 }),
    quote({ instrument_id: 'P340', strike: 340, delta: -0.6, bid: 9 }),
    quote({ instrument_id: 'P300-oct', strike: 300, expiry: '2026-10-23' }),
  ],
};

describe('option chain', () => {
  it('highlights |delta| from 0.08 to 0.15', () => {
    expect(inDeltaBand(-0.08)).toBe(true);
    expect(inDeltaBand(0.15)).toBe(true);
    expect(inDeltaBand(-0.16)).toBe(false);
    expect(inDeltaBand(null)).toBe(false);
  });

  it('keeps one expiry and right, near the money unless asked for all strikes', () => {
    const near = chainRows(chain, {
      right: 'P',
      expiry: '2026-11-20',
      symbol: 'AAPL',
      nearMoney: true,
    });
    expect(near.map((r) => [r.id, r.inBand])).toEqual([
      ['P300', true],
      ['P340', false],
    ]);
    const all = chainRows(chain, {
      right: 'P',
      expiry: '2026-11-20',
      symbol: 'AAPL',
      nearMoney: false,
    });
    expect(all.map((r) => r.id)).toEqual(['P100', 'P300', 'P340']);
    const calls = chainRows(chain, {
      right: 'C',
      expiry: '2026-11-20',
      symbol: 'AAPL',
      nearMoney: true,
    });
    expect(calls.map((r) => r.id)).toEqual(['C340']);
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

  it('opens on the first expiry three weeks out, and labels expiries with days', () => {
    expect(defaultExpiry(chain)).toBe('2026-10-23');
    expect(defaultExpiry({ ...chain, expiries: ['2026-10-05'] })).toBe('2026-10-05');
    expect(defaultExpiry({ ...chain, expiries: [] })).toBeNull();
    expect(expiryLabel('2026-10-02', '2026-11-20')).toBe('20 Nov · 49d');
    expect(spotOf(chain)).toBe(333.6);
    expect(spotOf({ ...chain, underlying: null })).toBeNull();
  });
});
