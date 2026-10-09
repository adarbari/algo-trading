import { describe, expect, it } from 'vitest';

import { activeFilterKeys, parseIdeasSearch } from './search';

describe('ideas search params', () => {
  it('keeps valid values and drops the rest (the default view is not kept)', () => {
    expect(
      parseIdeasSearch({
        view: 'conviction',
        screener: ' vrp-scanner ',
        decision: 'QUALIFIED',
        liq: 'risk',
        regime: 'CLOUDS',
        junk: 'x',
      }),
    ).toEqual({
      view: 'conviction',
      screener: 'vrp-scanner',
      decision: 'QUALIFIED',
      liq: 'risk',
      regime: 'CLOUDS',
    });
    expect(parseIdeasSearch({ view: 'top', liq: 'maybe', screener: '  ', regime: 4 })).toEqual({});
  });

  it('lists the filter chips in force, never the view', () => {
    expect(activeFilterKeys({ view: 'conviction', liq: 'ok', regime: 'X' })).toEqual([
      'liq',
      'regime',
    ]);
    expect(activeFilterKeys({})).toEqual([]);
  });
});
