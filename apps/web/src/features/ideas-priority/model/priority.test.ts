import { describe, expect, it } from 'vitest';

import type { IdeasResponse } from '@/entities/idea';

import { withPriority } from './priority';

const screener = (id: string) => ({
  screener: { id, name: id, owner: 'me', version: 1 },
  run: null,
  notRun: null,
  picked: 0,
  top: [],
});

describe('withPriority', () => {
  it('takes the new priority and orders the screeners by it, the unlisted last', () => {
    const response: IdeasResponse = {
      ideas: {
        session: '2026-10-02',
        priority: ['a', 'b'],
        total: 0,
        pausedTotal: 0,
        paused: [],
        screeners: [screener('a'), screener('b'), screener('c')],
        items: [],
      },
    };
    const next = withPriority(response, ['b', 'a']);
    expect(next.ideas?.priority).toEqual(['b', 'a']);
    expect(next.ideas?.screeners.map((s) => s.screener.id)).toEqual(['b', 'a', 'c']);
    expect(response.ideas?.priority).toEqual(['a', 'b']);
  });

  it('leaves an empty response alone', () => {
    const empty: IdeasResponse = { ideas: null };
    expect(withPriority(empty, ['a'])).toBe(empty);
  });
});
