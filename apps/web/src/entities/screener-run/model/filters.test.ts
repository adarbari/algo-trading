import { describe, expect, it } from 'vitest';

import { parseFilters } from './filters';

describe('parseFilters', () => {
  it('keeps trimmed text and drops anything else', () => {
    expect(parseFilters({ user: ' abhi ', screener: 'trend', status: 'failed' })).toEqual({
      user: 'abhi',
      screener: 'trend',
      status: 'failed',
    });
    expect(parseFilters({ user: '  ', screener: 4, status: null })).toEqual({});
  });
});
