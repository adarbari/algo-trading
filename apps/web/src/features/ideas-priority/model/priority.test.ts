import { describe, expect, it } from 'vitest';

import { withPriority } from './priority';

describe('withPriority', () => {
  it('replaces only the priority', () => {
    const response = {
      session: '2026-10-02',
      priority: ['a', 'b'],
      total: 0,
      screeners: [],
      items: [],
    };
    expect(withPriority(response, ['b', 'a'])).toEqual({ ...response, priority: ['b', 'a'] });
    expect(response.priority).toEqual(['a', 'b']);
  });
});
