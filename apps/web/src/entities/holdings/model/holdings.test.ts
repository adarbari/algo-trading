import { describe, expect, it } from 'vitest';

import { hasShort, shownWeight, sourceLabel, toRows, type EtfHoldings } from './holdings';

const HOLDINGS: EtfHoldings = {
  instrument_id: 'EQ:FUND',
  is_etf: true,
  as_of: '2026-10-01',
  source: 'ishares_holdings',
  total: 500,
  items: [
    {
      rank: 1,
      name: 'Apple',
      symbol: 'AAPL',
      instrument_id: 'EQ:AAPL',
      weight: 0.5,
      asset_class: 'Equity',
    },
    {
      rank: 2,
      name: 'Roper',
      symbol: 'ROP',
      instrument_id: null,
      weight: 0.25,
      asset_class: 'Equity',
    },
    { rank: 3, name: 'Cash', symbol: null, instrument_id: null, weight: 0.1, asset_class: null },
  ],
};

describe('holdings model', () => {
  it('links a holding only when its ticker is an instrument of the universe', () => {
    expect(toRows(HOLDINGS).map((r) => [r.ticker, r.symbol])).toEqual([
      ['AAPL', 'AAPL'],
      ['ROP', null], // printed with a ticker, not in the universe
      [null, null],
    ]);
  });

  it('adds up the shown weights by size, and sees a short line', () => {
    expect(shownWeight(HOLDINGS)).toBeCloseTo(0.85);
    const items = HOLDINGS.items
      .slice(0, 2)
      .map((item, i) => (i === 0 ? { ...item, weight: -0.9 } : item));
    const inverse = { ...HOLDINGS, items };
    expect(shownWeight(inverse)).toBeCloseTo(1.15);
    expect([hasShort(HOLDINGS), hasShort(inverse)]).toEqual([false, true]);
    expect(shownWeight({ ...HOLDINGS, items: [] })).toBe(0);
  });

  it('names the sources', () => {
    expect(sourceLabel('ssga_holdings')).toBe('State Street daily holdings file');
    expect(sourceLabel('ishares_holdings')).toBe('iShares daily holdings file');
    expect(sourceLabel('sec_nport')).toContain('N-PORT');
    expect(sourceLabel('other')).toBe('other');
    expect(sourceLabel(null)).toBeNull();
  });
});
