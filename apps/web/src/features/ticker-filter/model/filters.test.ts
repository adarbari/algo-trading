import { describe, expect, it } from 'vitest';

import { liquidityLabel, toTableFilters, typeLabel } from './filters';

describe('ticker filters', () => {
  it('sends every filter to the server, the search text trimmed', () => {
    expect(toTableFilters({ q: ' nv ', type: 'ETF', optionable: true, liquidity: 'HIGH' })).toEqual(
      {
        securityType: 'ETF',
        sector: undefined,
        liquidityClass: 'HIGH',
        leveraged: undefined,
        optionable: true,
        q: 'nv',
      },
    );
    expect(toTableFilters({ q: '  ' }).q).toBeUndefined();
  });

  it('names types and liquidity classes in words', () => {
    expect(typeLabel('COMMON_STOCK')).toBe('Stock');
    expect(typeLabel('PREFERRED')).toBe('Preferred');
    expect(liquidityLabel('MEDIUM')).toBe('Medium');
  });
});
