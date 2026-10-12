import { describe, expect, it } from 'vitest';

import { mergeNotes, notesOf, withNotes } from './notes';

describe('notes', () => {
  it('reads the notes of the draft, else of the base, and an empty list clears them', () => {
    const base = { notes: ['from preset'] };
    expect(notesOf(base, { id: 'my' })).toEqual(['from preset']);
    expect(notesOf(base, withNotes({ id: 'my' }, ['own']))).toEqual(['own']);
    expect(notesOf(base, withNotes({ id: 'my' }, [], base))).toEqual([]);
    expect(withNotes({ id: 'my' }, [], base)).toEqual({ id: 'my', notes: [] }); // clears the preset's
    expect(notesOf(null, { id: 'my' })).toEqual([]);
  });

  it('drops the notes key when the list is empty and the base had none (no `notes: []`)', () => {
    expect(withNotes({ id: 'my', notes: ['a'] }, [], {})).toEqual({ id: 'my' });
    expect(withNotes({ id: 'my', notes: ['a'] }, [], null)).not.toHaveProperty('notes');
    expect(withNotes({ id: 'my' }, ['a'], {})).toEqual({ id: 'my', notes: ['a'] });
  });

  it('merges notes without blanks or repeats, cut and capped like the server', () => {
    expect(mergeNotes(['a'], ['a', ' b ', ''])).toEqual(['a', 'b']);
    expect(mergeNotes([], ['x'.repeat(250)])[0]).toHaveLength(200);
    const many = Array.from({ length: 15 }, (_, i) => `note ${String(i)}`);
    expect(mergeNotes([], many)).toHaveLength(10);
  });
});
