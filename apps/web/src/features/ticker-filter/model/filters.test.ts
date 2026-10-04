import { describe, expect, it } from 'vitest';

import type { TickerRow } from '@/entities/explore';

import { liquidityLabel, matchesSearch, searchRows, toTickerQuery, typeLabel } from './filters';

const row = (symbol: string, name: string, values: Record<string, unknown> = {}): TickerRow => ({
  symbol,
  instrumentId: `EQ:${symbol}`,
  name,
  securityType: 'COMMON_STOCK',
  values,
});

const rows = [
  row('AAPL', 'Apple Inc.', { 'instrument.sector': 'Technology' }),
  row('NVDA', 'NVIDIA Corporation'),
  row('NVD', 'GraniteShares 2x Short NVDA Daily ETF'),
  row('KO', 'Coca-Cola'),
];

describe('ticker filters', () => {
  it('sends the server-side filters with the columns', () => {
    expect(
      toTickerQuery({ q: 'nv', type: 'ETF', optionable: true, liquidity: 'HIGH' }, ['a']),
    ).toEqual({
      securityType: 'ETF',
      sector: undefined,
      liquidityClass: 'HIGH',
      leveraged: undefined,
      optionable: true,
      columns: ['a'],
    });
  });

  it('searches tickers, names and text values, exact tickers first', () => {
    expect(matchesSearch(rows[0] as TickerRow, 'techno')).toBe(true);
    expect(searchRows(rows, 'nvda').map((r) => r.symbol)).toEqual(['NVDA', 'NVD']);
    expect(searchRows(rows, 'cola').map((r) => r.symbol)).toEqual(['KO']);
    expect(searchRows(rows, '  ')).toBe(rows);
    expect(searchRows(rows, undefined)).toBe(rows);
  });

  it('searches the whole universe in a few milliseconds', () => {
    const universe = Array.from({ length: 11_427 }, (_, i) =>
      row(`T${i}`, `Ticker number ${i}`, { 'instrument.sector': i % 2 ? 'Energy' : 'Utilities' }),
    );
    const started = performance.now();
    const found = searchRows(universe, 'number 1142');
    const elapsed = performance.now() - started;
    expect(found.map((r) => r.symbol)).toEqual([
      'T1142',
      ...Array.from({ length: 7 }, (_, i) => `T1142${i}`),
    ]);
    expect(elapsed).toBeLessThan(100);
  });

  it('names types and liquidity classes in words', () => {
    expect(typeLabel('COMMON_STOCK')).toBe('Stock');
    expect(typeLabel('PREFERRED')).toBe('Preferred');
    expect(liquidityLabel('MEDIUM')).toBe('Medium');
  });
});
