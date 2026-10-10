import { describe, expect, it } from 'vitest';

import { blankDraft } from './draft';
import { clearStash, NEW_KEY, stash, unstash } from './stash';

describe('stash', () => {
  it('keeps one draft per edge, with the screens known then, until it is cleared', () => {
    const draft = { ...blankDraft(), name: 'kept' };
    stash('mine', draft, ['a']);
    expect(unstash('mine')).toEqual({ draft, known: ['a'] });
    expect(unstash(NEW_KEY)).toBeUndefined();
    clearStash('mine');
    expect(unstash('mine')).toBeUndefined();
  });
});
