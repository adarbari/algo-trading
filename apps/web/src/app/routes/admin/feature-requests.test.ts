import { describe, expect, it } from 'vitest';

import { validateFeatureRequestsSearch } from './feature-requests';

describe('validateFeatureRequestsSearch', () => {
  it('keeps a chosen status, else nothing (the list ignores one it does not serve)', () => {
    expect(validateFeatureRequestsSearch({ status: 'WONT_DO' })).toEqual({ status: 'WONT_DO' });
    expect(validateFeatureRequestsSearch({ status: '' })).toEqual({});
    expect(validateFeatureRequestsSearch({ status: 3 })).toEqual({});
    expect(validateFeatureRequestsSearch({})).toEqual({});
  });
});
