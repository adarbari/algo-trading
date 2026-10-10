import { describe, expect, it } from 'vitest';

import { blankDraft } from './draft';
import { clearStash, NEW_KEY, stash, unstash } from './stash';

describe('stash', () => {
  it('keeps one draft per edge until it is cleared', () => {
    const draft = { ...blankDraft(), name: 'kept' };
    stash('mine', draft);
    expect(unstash('mine')).toBe(draft);
    expect(unstash(NEW_KEY)).toBeUndefined();
    clearStash('mine');
    expect(unstash('mine')).toBeUndefined();
  });
});
