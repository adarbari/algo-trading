import { describe, expect, it } from 'vitest';

import { validateLlmUsageSearch } from './llm-usage';

describe('validateLlmUsageSearch', () => {
  it('keeps a chosen call, else nothing', () => {
    expect(validateLlmUsageSearch({ call: 'ts~claude~regime' })).toEqual({
      call: 'ts~claude~regime',
    });
    expect(validateLlmUsageSearch({ call: '' })).toEqual({});
    expect(validateLlmUsageSearch({ call: 3 })).toEqual({});
    expect(validateLlmUsageSearch({})).toEqual({});
  });
});
