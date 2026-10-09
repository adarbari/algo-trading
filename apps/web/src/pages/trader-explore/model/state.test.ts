import { describe, expect, it } from 'vitest';

import { chooseTicker, closeTicker, exploreState, MAX_OPEN, openTicker } from './state';

describe('exploreState', () => {
  it('reads the open tickers, the focus and the defaults', () => {
    expect(exploreState({ sel: 'AAPL,MSFT' })).toMatchObject({
      open: ['AAPL', 'MSFT'],
      focused: 'AAPL',
      tab: 'compare',
      range: '1Y',
      via: null,
    });
    expect(exploreState({ sel: 'AAPL,MSFT', focus: 'MSFT' })).toMatchObject({
      focused: 'MSFT',
      tab: 'overview',
    });
    expect(exploreState({})).toMatchObject({ open: [], focused: null, tab: 'overview' });
  });

  it('opens a focus that is not in the list, and caps the tabs at MAX_OPEN keeping the focus', () => {
    expect(exploreState({ sel: 'A', focus: 'B' }).open).toEqual(['A', 'B']);
    const many = Array.from({ length: MAX_OPEN + 2 }, (_, i) => `T${String(i)}`);
    const state = exploreState({ sel: many.join(','), focus: 'T0' });
    expect(state.open).toHaveLength(MAX_OPEN);
    expect(state.open).toContain('T0');
  });

  it('never selects Compare for one ticker or Why without a screener', () => {
    expect(exploreState({ sel: 'A', tab: 'compare' }).tab).toBe('overview');
    expect(exploreState({ sel: 'A', tab: 'why' }).tab).toBe('overview');
    expect(exploreState({ sel: 'A', tab: 'why', via: 'vrp' }).tab).toBe('why');
  });
});

describe('opening and closing tabs', () => {
  const state = exploreState({ sel: 'A,B,C', focus: 'B', via: 'vrp' });

  it('opens a new ticker last and selects it; an open one is only selected', () => {
    expect(openTicker(state, 'D')).toMatchObject({ sel: 'A,B,C,D', focus: 'D', via: undefined });
    expect(openTicker(state, 'A')).toMatchObject({ sel: 'A,B,C', focus: 'A' });
  });

  it('gives way to the oldest tab when full, never the new one', () => {
    const full = exploreState({ sel: 'A,B,C,D,E,F' });
    expect(openTicker(full, 'G')).toMatchObject({ sel: 'B,C,D,E,F,G', focus: 'G' });
  });

  it('chooses a tab, resetting what belongs to the ticker', () => {
    expect(chooseTicker(state, 'C')).toEqual({
      sel: 'A,B,C',
      focus: 'C',
      expiry: undefined,
      feature: undefined,
      via: undefined,
    });
  });

  it('closes a tab: the neighbour on the right takes the selection, else the left', () => {
    expect(closeTicker(state, 'B')).toMatchObject({ sel: 'A,C', focus: 'C' });
    expect(closeTicker(exploreState({ sel: 'A,B', focus: 'B' }), 'B')).toMatchObject({
      sel: 'A',
      focus: 'A',
    });
    expect(closeTicker(state, 'C')).toEqual({ sel: 'A,B', focus: 'B' });
    expect(closeTicker(exploreState({ sel: 'A' }), 'A')).toMatchObject({
      sel: undefined,
      focus: undefined,
    });
  });
});
