import { describe, expect, it } from 'vitest';

import { validateHarnessRunsSearch } from './harness-runs';

describe('validateHarnessRunsSearch', () => {
  it('keeps a chosen run, else nothing', () => {
    expect(validateHarnessRunsSearch({ run: 'abc123' })).toEqual({ run: 'abc123' });
    expect(validateHarnessRunsSearch({ run: '' })).toEqual({});
    expect(validateHarnessRunsSearch({ run: 3 })).toEqual({});
    expect(validateHarnessRunsSearch({})).toEqual({});
  });
});
