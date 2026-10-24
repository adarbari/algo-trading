import { describe, expect, it } from 'vitest';

import { parseIdeasSearch } from './search';

describe('ideas search params', () => {
  it('keeps the options column set, and drops the default and unknown ones', () => {
    expect(parseIdeasSearch({ columns: 'options' })).toEqual({ columns: 'options' });
    expect(parseIdeasSearch({ columns: 'stocks' })).toEqual({});
    expect(parseIdeasSearch({ columns: 'futures' })).toEqual({});
  });

  it('drops the filter keys of the old chips (the filter bar owns `f`)', () => {
    expect(parseIdeasSearch({ view: 'conviction', decision: 'QUALIFIED', liq: 'risk' })).toEqual(
      {},
    );
  });
});
