import { describe, expect, it } from 'vitest';

import { decodeFilters } from './codec';
import { filterSearch } from './search';

describe('filterSearch', () => {
  it('keeps an f with an entry as written, trimmed', () => {
    expect(filterSearch({ f: ' dte:..14;junk;dte:..3 ' })).toEqual({ f: 'dte:..14;junk;dte:..3' });
  });

  it('drops absent, non-string, blank and entry-less values', () => {
    expect(filterSearch({})).toEqual({});
    expect(filterSearch({ f: 5 })).toEqual({});
    expect(filterSearch({ f: '  ' })).toEqual({});
    expect(filterSearch({ f: 'garbage' })).toEqual({});
  });

  it('leaves malformed entries to the decoder, which drops them', () => {
    const kept = filterSearch({ f: 'dte:..14;junk;dte:..3;x:..' }).f;
    expect(decodeFilters(kept).map((x) => x.id)).toEqual(['dte']);
  });
});
