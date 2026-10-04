import { describe, expect, it } from 'vitest';

import { compareSearch } from './compare-search';

describe('compareSearch', () => {
  it('is null for nothing', () => {
    expect(compareSearch([])).toBeNull();
  });

  it('keeps pick order, focuses the first, caps at six', () => {
    expect(compareSearch(['MSFT', 'AAPL'])).toEqual({ sel: 'MSFT,AAPL', focus: 'MSFT' });
    expect(compareSearch(['A', 'B', 'C', 'D', 'E', 'F', 'G'])?.sel).toBe('A,B,C,D,E,F');
  });
});
