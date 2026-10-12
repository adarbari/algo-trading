import { describe, expect, it } from 'vitest';

import { partEdited, partsOf, suggestionsOf, type DraftPart } from './parts';
import type { ScreenDraft } from './review';

const answer = (extra: Record<string, unknown>): ScreenDraft => ({
  screener_id: 's',
  document: {},
  dropped: [],
  notes: [],
  ...extra,
});

const PART = {
  id: 'p1',
  words: 'liquid',
  start: 0,
  end: 6,
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
    expect(parts[0]).toMatchObject({ kind: 'needs_choice', reading_source: 'model' });
  });

  it('is empty for an answer with none (absent, null, not a list)', () => {
    expect(partsOf(answer({}))).toEqual([]);
    expect(partsOf(answer({ parts: null }))).toEqual([]);
    expect(partsOf(answer({ parts: 'x' }))).toEqual([]);
  });

  it('skips a malformed entry and defaults what is missing from a good one', () => {
    const parts = partsOf(
      answer({
        parts: [null, { id: 'p1' }, { id: 'p2', kind: 'nope' }, { id: 'p3', kind: 'applied' }],
      }),
    );
    expect(parts).toHaveLength(1);
    expect(parts[0]).toMatchObject({
      id: 'p3',
      words: '',
      reading: null,
      reading_source: null,
      origin: 'words',
      criteria: [],
      suggestions: [],
    });
  });

  it('treats an empty reading as none', () => {
    expect(partsOf(answer({ parts: [{ ...PART, reading: '' }] }))[0]?.reading).toBeNull();
  });
});

describe('suggestionsOf', () => {
  const s = (mode: string, id?: string) => ({
    ...(id ? { id } : {}),
    criterion: { field: 'f.x', mode },
    source: null,
    why: 'w',
  });

  it('keeps the server id, else the position', () => {
    const found = suggestionsOf(answer({ suggestions: [s('soft', 'a'), s('score')] }));
    expect(found.map((x) => x.id)).toEqual(['a', '2']);
  });

  it('offers soft and score checks only', () => {
    const found = suggestionsOf(answer({ suggestions: [s('hard', 'h'), s('soft', 'a')] }));
    expect(found.map((x) => x.id)).toEqual(['a']);
    expect(suggestionsOf(answer({}))).toEqual([]);
  });
});

describe('partEdited', () => {
  const part = PART as unknown as DraftPart;
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
    expect(partEdited(part, original, { ...original }, terms)).toBe(false);
  });

  it('is false for a pick of another reading of the part own term', () => {
    const current = { ...original, dv: { ...original.dv, value: 10 } };
    expect(partEdited(part, original, current, terms)).toBe(false);
  });

  it('is true when a key outside the readings changed', () => {
    const current = { ...original, dv: { ...original.dv, mode: 'soft' } };
    expect(partEdited(part, original, current, terms)).toBe(true);
  });

  it('is true when the value changed and the part has no reading to pick', () => {
    const current = { ...original, dv: { ...original.dv, value: 10 } };
    expect(partEdited({ ...part, unresolved: [] }, original, current, terms)).toBe(true);
  });

  it('is true when the trader removed the row, false for a row another part owns', () => {
    expect(partEdited(part, original, { other: original.other }, terms)).toBe(true);
    expect(partEdited(part, original, { dv: original.dv }, terms)).toBe(false);
  });

  it('is false for a part with no criteria, and for an answer with no original rows', () => {
    expect(partEdited({ ...part, criteria: [] }, original, {}, terms)).toBe(false);
    expect(partEdited(part, undefined, {}, undefined)).toBe(false);
  });
});
