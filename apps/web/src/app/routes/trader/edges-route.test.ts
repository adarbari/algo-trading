import { describe, expect, it } from 'vitest';

import { validateBuilderSearch, validateEdgesSearch } from './edges-route';

describe('validateEdgesSearch', () => {
  it('keeps a chosen edge id and drops anything else', () => {
    expect(validateEdgesSearch({ edge: 'momentum_12_1' })).toEqual({ edge: 'momentum_12_1' });
    expect(validateEdgesSearch({ edge: '' })).toEqual({});
    expect(validateEdgesSearch({ edge: 3 })).toEqual({});
    expect(validateEdgesSearch({})).toEqual({});
  });
});

describe('validateBuilderSearch', () => {
  it('keeps the screen to add and drops anything else', () => {
    expect(validateBuilderSearch({ screen: 'momo' })).toEqual({ screen: 'momo' });
    expect(validateBuilderSearch({ screen: '' })).toEqual({});
    expect(validateBuilderSearch({ screen: 1 })).toEqual({});
  });
});
