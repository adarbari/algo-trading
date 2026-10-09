import { describe, expect, it } from 'vitest';

import { changesOf, decisionSegments } from './summary';

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

describe('decisionSegments', () => {
  it('keeps the picks in display order with their tones and leaves the rejects out', () => {
    expect(
      decisionSegments([
        { decision: 'REJECT', count: 4000 },
        { decision: 'WATCH', count: 6 },
        { decision: 'QUALIFIED', count: 14 },
      ]),
    ).toEqual([
      { id: 'QUALIFIED', label: 'Qualified', value: 14, tone: 'positive' },
      { id: 'WATCH', label: 'Watch', value: 6, tone: 'accent' },
    ]);
  });
});
