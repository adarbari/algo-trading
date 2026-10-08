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
