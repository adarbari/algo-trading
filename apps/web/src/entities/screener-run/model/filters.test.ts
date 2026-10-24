import { describe, expect, it } from 'vitest';

import { parseFilters } from './filters';
import { RUN_STATUSES } from './labels';

describe('parseFilters', () => {
  it('keeps trimmed text and drops anything else', () => {
    expect(parseFilters({ user: ' abhi ', screener: 'trend', status: 'failed' })).toEqual({
      user: 'abhi',
      screener: 'trend',
      status: 'FAILED',
    });
    expect(parseFilters({ user: '  ', screener: 4, status: null })).toEqual({});
  });

  it('keeps only a status the API enum has, in any case, and drops a typo', () => {
    expect(parseFilters({ status: 'Partial' })).toEqual({ status: 'PARTIAL' });
    expect(parseFilters({ status: 'faild' })).toEqual({});
  });

  it('lists every status of the generated enum', () => {
    expect([...RUN_STATUSES].sort()).toEqual([
      'COMPLETE',
      'FAILED',
      'PARTIAL',
      'QUEUED',
      'RUNNING',
      'WAITING',
    ]);
  });
});
