import { describe, expect, it } from 'vitest';

import { validateScreenersSearch } from './screeners-route';

describe('validateScreenersSearch', () => {
  it('keeps the filter bar state in canonical form and the search text', () => {
    expect(validateScreenersSearch({ f: 'owner:mine;picked:1..', q: 'vrp' })).toEqual({
      f: 'owner:mine;picked:1..',
      q: 'vrp',
    });
  });

  it('drops garbage and a blank search', () => {
    expect(validateScreenersSearch({ f: 'nonsense', q: ' ' })).toEqual({});
    expect(validateScreenersSearch({ f: 3, q: 7 })).toEqual({});
  });
});
