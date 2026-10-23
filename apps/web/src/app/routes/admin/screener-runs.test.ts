import { describe, expect, it } from 'vitest';

import { validateScreenerRunsSearch } from './screener-runs';

describe('validateScreenerRunsSearch', () => {
  it('keeps a chosen run and the filters, drops anything else', () => {
    expect(
      validateScreenerRunsSearch({
        run: 'r1',
        user: 'abhi',
        screener: ' trend ',
        status: 'failed',
      }),
    ).toEqual({ run: 'r1', user: 'abhi', screener: 'trend', status: 'failed' });
    expect(validateScreenerRunsSearch({ run: '', user: '', status: 3 })).toEqual({});
    expect(validateScreenerRunsSearch({})).toEqual({});
  });
});
