import { describe, expect, it } from 'vitest';

import type { DraftPart } from './parts';
import type { ScreenDraft } from './review';
import { sentenceSegments } from './sentence';

const PART: Omit<DraftPart, 'id' | 'kind' | 'words' | 'start' | 'end'> = {
  rank: false,
  join_words: '',
  reading: null,
  reading_source: 'model',
  origin: 'words',
  criteria: [],
  dropped: [],
  formulas: [],
  unresolved: [],
  missing: [],
};

const SENTENCE = 'liquid stocks but not before earnings and held two years';

function part(id: string, kind: DraftPart['kind'], words: string): DraftPart {
  const start = SENTENCE.indexOf(words);
  return { ...PART, id, kind, words, start, end: start + words.length };
}

function answer(parts: DraftPart[] | null): ScreenDraft {
  return {
    screener_id: 's',
    document: {},
    dropped: [],
    notes: [],
    sentence: SENTENCE,
    parts,
  };
}

describe('sentenceSegments', () => {
  it('tags each part by its kind and keeps the connectors plain, in sentence order', () => {
    const got = sentenceSegments(
      answer([
        part('p3', 'not_available', 'held two years'),
        part('p1', 'needs_choice', 'liquid stocks'),
        part('p2', 'applied', 'not before earnings'),
      ]),
    );
    expect(got.map((s) => [s.text, s.kind, s.label])).toEqual([
      ['liquid stocks', 'ask', 'Needs your call'],
      ['but', 'plain', undefined],
      ['not before earnings', 'applied', 'Applied'],
      ['and', 'plain', undefined],
      ['held two years', 'gap', 'Not available yet'],
    ]);
  });

  it('shows words nothing understood as a tagged gap, never as plain text', () => {
    const got = sentenceSegments(answer([part('g1', 'not_understood', 'held two years')]));
    expect(got.at(-1)).toMatchObject({ kind: 'gap', label: 'Not understood' });
  });

  it('leaves out a part without words and keeps the sentence whole without parts', () => {
    const kept = { ...PART, id: 'kept', kind: 'applied', words: '', start: 0, end: 0 } as const;
    expect(sentenceSegments(answer([kept]))).toEqual([
      { id: 'plain-0', text: SENTENCE, kind: 'plain' },
    ]);
    expect(sentenceSegments(answer(null))).toEqual([
      { id: 'plain-0', text: SENTENCE, kind: 'plain' },
    ]);
  });
});
