import { describe, expect, it } from 'vitest';

import { byteLength, fitToCap, isPersistableKey, type StoredQuery } from './persist-cap';

function query(hash: string, at: number, filler = 0): StoredQuery {
  return {
    queryHash: hash,
    queryKey: ['gql', 'Page', { hash }],
    state: { dataUpdatedAt: at, data: 'x'.repeat(filler) } as StoredQuery['state'],
  };
}

const hashes = (json: string) => (JSON.parse(json) as StoredQuery[]).map((q) => q.queryHash);

describe('isPersistableKey', () => {
  it('keeps GraphQL page reads', () => {
    expect(isPersistableKey(['gql', 'IdeasPage', {}])).toBe(true);
  });

  it('never keeps the viewer, live quotes, admin polling or any REST / job / preview key', () => {
    for (const key of [
      ['gql', 'Viewer', {}],
      ['gql', 'OptionQuotes', {}],
      ['gql', 'NightlyRuns', {}],
      ['screeners', 'preview', {}],
      ['screeners', 'run', 'a', 'job'],
      ['edges', 'evaluation', 'a', 'job'],
      ['features', 'check', 'x'],
      ['health'],
    ]) {
      expect(isPersistableKey(key), JSON.stringify(key)).toBe(false);
    }
  });
});

describe('fitToCap', () => {
  it('keeps everything under the cap', () => {
    const fitted = fitToCap([query('a', 1), query('b', 2)], new Map(), 10_000);
    expect(fitted).toMatchObject({ kept: 2, dropped: 0 });
  });

  it('drops the least recently used queries first when the record would exceed the cap', () => {
    const queries = [query('old', 1, 400), query('mid', 2, 400), query('new', 3, 400)];
    const fitted = fitToCap(queries, new Map(), 1024 + 1000);
    expect(hashes(fitted.queriesJson)).toEqual(['new', 'mid']);
    expect(fitted.dropped).toBe(1);
  });

  it('orders by last use, not by when the data arrived', () => {
    const queries = [query('a', 1, 400), query('b', 2, 400), query('c', 3, 400)];
    const fitted = fitToCap(queries, new Map([['a', 99]]), 1024 + 1000);
    expect(hashes(fitted.queriesJson)).toEqual(['a', 'c']);
  });

  it('measures serialized bytes (multi-byte text), not characters', () => {
    const wide = { ...query('w', 1), state: { dataUpdatedAt: 1, data: '€'.repeat(300) } };
    // 300 characters are 900 bytes: under 1500 by length alone, over it in bytes.
    const fitted = fitToCap([wide as StoredQuery], new Map(), 1024 + 500);
    expect(fitted.kept).toBe(0);
    expect(byteLength('€')).toBe(3);
  });

  it('drops one query bigger than the cap without evicting the others', () => {
    const queries = [query('small', 1, 10), query('huge', 2, 5000)];
    const fitted = fitToCap(queries, new Map(), 1024 + 1000);
    expect(hashes(fitted.queriesJson)).toEqual(['small']);
  });
});
