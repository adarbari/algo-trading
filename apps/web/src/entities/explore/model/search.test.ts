import { describe, expect, it } from 'vitest';

import { DEFAULT_DIMENSIONS, joinList, parseExploreSearch, splitList } from './search';

describe('explore search params', () => {
  it('keeps valid values and drops the rest', () => {
    expect(
      parseExploreSearch({
        sel: 'aapl,MSFT',
        tab: 'options',
        range: '2Y',
        view: 'weird',
        unknown: 'x',
      }),
    ).toEqual({ sel: 'AAPL,MSFT', tab: 'options', range: '2Y' });
    expect(parseExploreSearch({ tab: 'nope', right: 'X', sel: '  ' })).toEqual({});
  });

  it('drops the retired table state and Field guide tab (an old link opens the default view)', () => {
    expect(
      parseExploreSearch({ tab: 'guide', theme: 'volatility', q: 'x', cols: 'a', lev: true }),
    ).toEqual({});
  });

  it('keeps the Why tab and the screener that surfaced the ticker (via)', () => {
    expect(parseExploreSearch({ sel: 'AAPL', tab: 'why', via: ' vrp-scanner ' })).toEqual({
      sel: 'AAPL',
      tab: 'why',
      via: 'vrp-scanner',
    });
    expect(parseExploreSearch({ via: '  ' })).toEqual({});
  });

  it('splits and joins lists, leaving defaults out of the URL', () => {
    expect(splitList('a, b,,c')).toEqual(['a', 'b', 'c']);
    expect(splitList(undefined)).toEqual([]);
    expect(joinList(DEFAULT_DIMENSIONS, DEFAULT_DIMENSIONS)).toBeUndefined();
    expect(joinList(['x', 'y'], DEFAULT_DIMENSIONS)).toBe('x,y');
    expect(joinList([], DEFAULT_DIMENSIONS)).toBe('none');
    expect(splitList('none')).toEqual([]);
  });
});
