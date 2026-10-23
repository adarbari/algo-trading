import { describe, expect, it } from 'vitest';

import { filterSearch } from './search';

describe('filterSearch', () => {
  it('keeps a valid f in its canonical spelling', () => {
    expect(filterSearch({ f: 'dte:..14;junk;dte:..3' })).toEqual({ f: 'dte:..14' });
  });

  it('drops absent, non-string and empty-after-decoding values', () => {
    expect(filterSearch({})).toEqual({});
    expect(filterSearch({ f: 5 })).toEqual({});
    expect(filterSearch({ f: 'garbage' })).toEqual({});
  });
});
