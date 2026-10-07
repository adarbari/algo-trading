import { describe, expect, it } from 'vitest';

import {
  DEFAULT_COLUMNS,
  formatSort,
  joinList,
  parseExploreSearch,
  parseSort,
  splitList,
} from './search';

describe('explore search params', () => {
  it('keeps valid values and drops the rest', () => {
    expect(
      parseExploreSearch({
        sel: 'aapl,MSFT',
        tab: 'options',
        lev: 'true',
        opt: true,
        range: '2Y',
        view: 'weird',
        unknown: 'x',
        q: 123,
      }),
    ).toEqual({ sel: 'AAPL,MSFT', tab: 'options', lev: true, opt: true, range: '2Y', q: '123' });
    expect(parseExploreSearch({ tab: 'nope', right: 'X', sel: '  ' })).toEqual({});
  });

  it("keeps the field guide's theme, field and symbol", () => {
    expect(
      parseExploreSearch({ tab: 'guide', theme: 'Volatility', field: 'feature.x', symbol: 'aapl' }),
    ).toEqual({ tab: 'guide', theme: 'Volatility', field: 'feature.x', symbol: 'AAPL' });
  });

  it('splits and joins lists, leaving defaults out of the URL', () => {
    expect(splitList('a, b,,c')).toEqual(['a', 'b', 'c']);
    expect(splitList(undefined)).toEqual([]);
    expect(joinList(DEFAULT_COLUMNS, DEFAULT_COLUMNS)).toBeUndefined();
    expect(joinList(['x', 'y'], DEFAULT_COLUMNS)).toBe('x,y');
    expect(joinList([], DEFAULT_COLUMNS)).toBe('none');
    expect(splitList('none')).toEqual([]);
  });

  it('round-trips the sort', () => {
    expect(parseSort('-rollup.iv30@v1.iv30')).toEqual({
      columnId: 'rollup.iv30@v1.iv30',
      direction: 'desc',
    });
    expect(formatSort({ columnId: 'symbol', direction: 'asc' })).toBe('symbol');
    expect(parseSort(undefined)).toBeNull();
    expect(formatSort(null)).toBeUndefined();
  });
});
