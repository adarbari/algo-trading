import { describe, expect, it } from 'vitest';

import { validateTestSearch } from './test-route';

describe('validateTestSearch', () => {
  it('keeps the filter bar state in canonical form and the search text', () => {
    expect(validateTestSearch({ f: 'owner:mine;picked:1..', q: 'vrp' })).toEqual({
      f: 'owner:mine;picked:1..',
      q: 'vrp',
    });
  });

  it('drops garbage and a blank search', () => {
    expect(validateTestSearch({ f: 'nonsense', q: ' ' })).toEqual({});
    expect(validateTestSearch({ f: 3, q: 7 })).toEqual({});
  });
});
