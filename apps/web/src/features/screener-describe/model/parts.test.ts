import { describe, expect, it } from 'vitest';

import { partEdited, partsOf, suggestionsOf, type DraftPart } from './parts';
import type { ScreenDraft } from './review';

const answer = (extra: Partial<ScreenDraft>): ScreenDraft => ({
  screener_id: 's',
  document: {},
  dropped: [],
  notes: [],
  ...extra,
});

const PART: DraftPart = {
  id: 'p1',
  words: 'liquid',
  start: 0,
  end: 6,
  rank: false,
  reading: 'over $50M traded a day',
  reading_source: 'model',
  kind: 'needs_choice',
  origin: 'words',
  criteria: ['dv'],
  dropped: [],
  formulas: [],
  unresolved: ['liquid'],
  missing: [],
  suggestions: [],
};

describe('partsOf', () => {
  it('reads the parts of an answer in order', () => {
    const parts = partsOf(answer({ parts: [PART, { ...PART, id: 'p2', words: 'stocks' }] }));
    expect(parts.map((p) => p.id)).toEqual(['p1', 'p2']);
  });

  it('is empty for an answer with none (absent, null, empty)', () => {
    expect(partsOf(answer({}))).toEqual([]);
    expect(partsOf(answer({ parts: null }))).toEqual([]);
    expect(partsOf(answer({ parts: [] }))).toEqual([]);
  });
});

describe('suggestionsOf', () => {
  const s = (mode: string, id: string) => ({
    id,
    criterion: { field: 'f.x', mode },
    source: null,
    why: 'w',
  });

  it('offers soft and score checks only, whatever arrives', () => {
    const found = suggestionsOf(
      answer({ suggestions: [s('hard', 'h'), s('soft', 'a'), s('score', 'b')] }),
    );
    expect(found.map((x) => x.id)).toEqual(['a', 'b']);
    expect(suggestionsOf(answer({}))).toEqual([]);
  });
});

describe('partEdited', () => {
  const original = {
    dv: { field: 'f.dv', op: 'gte', value: 50, mode: 'hard' },
    other: { field: 'f.o' },
  };
  const terms = [
    {
      term: 'liquid',
      span: 'liquid',
      default_index: 0,
      alternatives: [
        { text: 'a', criterion: { field: 'f.dv', op: 'gte', value: 50 } },
        { text: 'b', criterion: { field: 'f.dv', op: 'gte', value: 10 } },
      ],
    },
  ];

  it('is false for the answer rows as they came', () => {
    expect(partEdited(PART, original, { ...original }, terms)).toBe(false);
  });

  it('is false for a pick of another reading of the part own term', () => {
    const current = { ...original, dv: { ...original.dv, value: 10 } };
    expect(partEdited(PART, original, current, terms)).toBe(false);
  });

  it('is true for a typed value that is none of the offered readings', () => {
    const current = { ...original, dv: { ...original.dv, value: 37 } };
    expect(partEdited(PART, original, current, terms)).toBe(true);
  });

  it('is true when a key outside the readings changed', () => {
    const current = { ...original, dv: { ...original.dv, mode: 'soft' } };
    expect(partEdited(PART, original, current, terms)).toBe(true);
  });

  it('is true when the value changed and the part has no reading to pick', () => {
    const current = { ...original, dv: { ...original.dv, value: 10 } };
    expect(partEdited({ ...PART, unresolved: [] }, original, current, terms)).toBe(true);
  });

  it('is true when the trader removed the row, false for a row another part owns', () => {
    expect(partEdited(PART, original, { other: original.other }, terms)).toBe(true);
    expect(partEdited(PART, original, { dv: original.dv }, terms)).toBe(false);
  });

  it('is false for a part with no criteria, and for an answer with no original rows', () => {
    expect(partEdited({ ...PART, criteria: [] }, original, {}, terms)).toBe(false);
    expect(partEdited(PART, undefined, {}, undefined)).toBe(false);
  });
});
