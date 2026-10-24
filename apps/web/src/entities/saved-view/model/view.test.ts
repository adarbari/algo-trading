import { describe, expect, it } from 'vitest';

import { restorableFilters } from './view';

describe('restorableFilters', () => {
  it('keeps what the surface defines and any id under the made-on-the-fly prefix, and names the rest', () => {
    const f = 'decision:QUALIFIED;gone:x;feature%3Arollup.a%40v1.b:1..';
    expect(restorableFilters(f, ['decision'], 'feature:')).toEqual({
      f: 'decision:QUALIFIED;feature%3Arollup.a%40v1.b:1..',
      dropped: ['gone'],
    });
    expect(restorableFilters(f, ['decision']).dropped).toEqual(['gone', 'feature:rollup.a@v1.b']);
    expect(restorableFilters(f, undefined)).toEqual({ f, dropped: [] });
  });
});
