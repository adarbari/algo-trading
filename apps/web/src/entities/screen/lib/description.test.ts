import { describe, expect, it } from 'vitest';

import { descriptionOf, MAX_DESCRIPTION_LENGTH, oneLine, withDescription } from './description';

describe('description', () => {
  it('turns newlines into one line and cuts to 140 characters', () => {
    expect(oneLine('a\n\nb\r\n c')).toBe('a b c');
    expect(oneLine('x'.repeat(200))).toHaveLength(MAX_DESCRIPTION_LENGTH);
  });

  it('reads the draft first, then the base, else empty', () => {
    expect(descriptionOf({ description: 'base' }, { id: 'a', description: 'own' })).toBe('own');
    expect(descriptionOf({ description: 'base' }, { id: 'a' })).toBe('base');
    expect(descriptionOf(null, { id: 'a' })).toBe('');
  });

  it('sets the description as one line', () => {
    expect(withDescription({ id: 'a' }, 'one\ntwo')).toEqual({ id: 'a', description: 'one two' });
  });
});
