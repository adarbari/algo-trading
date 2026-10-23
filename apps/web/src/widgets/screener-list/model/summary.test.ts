import { describe, expect, it } from 'vitest';

import { changesOf } from './summary';

describe('changesOf', () => {
  it('reads the served new and dropped counts, none without a previous run', () => {
    expect(
      changesOf([
        { change: 'new', count: 5 },
        { change: 'dropped', count: 2 },
      ]),
    ).toEqual({ added: 5, dropped: 2 });
    expect(changesOf([{ change: 'new', count: 1 }])).toEqual({ added: 1, dropped: 0 });
    expect(changesOf([])).toBeNull();
  });
});
