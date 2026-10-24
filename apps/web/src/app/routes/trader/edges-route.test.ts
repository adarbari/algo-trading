import { describe, expect, it } from 'vitest';

import { validateEdgesSearch } from './edges-route';

describe('validateEdgesSearch', () => {
  it('keeps a chosen edge id and drops anything else', () => {
    expect(validateEdgesSearch({ edge: 'momentum_12_1' })).toEqual({ edge: 'momentum_12_1' });
    expect(validateEdgesSearch({ edge: '' })).toEqual({});
    expect(validateEdgesSearch({ edge: 3 })).toEqual({});
    expect(validateEdgesSearch({})).toEqual({});
  });
});

describe('validateEdgesSearch, the list narrowing', () => {
  it('keeps the filter bar state in canonical form and the search text', () => {
    expect(validateEdgesSearch({ f: 'status:rejected;!mine:', q: 'drift' })).toEqual({
      f: 'status:rejected;!mine:',
      q: 'drift',
    });
    expect(validateEdgesSearch({ f: 'garbage', q: '  ' })).toEqual({});
  });

  it('maps a legacy ?view= link onto the filters it stood for', () => {
    expect(validateEdgesSearch({ view: 'mine' })).toEqual({ f: 'mine:' });
    expect(validateEdgesSearch({ view: 'following' })).toEqual({ f: 'followed:' });
    expect(validateEdgesSearch({ view: 'rejected', edge: 'x' })).toEqual({
      edge: 'x',
      f: 'status:rejected',
    });
    expect(validateEdgesSearch({ view: 'bogus' })).toEqual({});
  });

  it('lets an explicit f win over a legacy view', () => {
    expect(validateEdgesSearch({ view: 'mine', f: 'followed:' })).toEqual({ f: 'followed:' });
  });
});
