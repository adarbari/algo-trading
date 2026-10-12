import { describe, expect, it } from 'vitest';

import { toCriterion } from '@/entities/screen';

import { baselineAfter, partEdited, partsOf, suggestionsOf, type DraftPart } from './parts';
import { readingSwap } from './readings';
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

describe('partEdited on server-shaped rows (no mode)', () => {
  const FIFTY = { field: 'f.dv', op: 'gte', value: 50 };
  const TEN = { field: 'f.dv', op: 'gte', value: 10 };
  const term = {
    term: 'liquid',
    span: 'liquid',
    default_index: 0,
    alternatives: [
      { text: 'a', criterion: FIFTY },
      { text: 'b', criterion: TEN },
    ],
  };
  const original = { dv: { ...FIFTY } };
  const swapped = (from: number, to: number, document: Record<string, Record<string, unknown>>) => {
    const swap = readingSwap({ id: 's', criteria: document }, term, from, to);
    if (!swap) throw new Error('no swap');
    const { id: _id, ...table } = swap;
    return { dv: table };
  };

  it('is false after a pick, and after picking the default back', () => {
    const picked = swapped(0, 1, original);
    expect(partEdited(PART, original, picked, [term])).toBe(false);
    expect(partEdited(PART, original, swapped(1, 0, picked), [term])).toBe(false);
    expect(toCriterion('dv', picked.dv).mode).toBe('hard');
  });

  it('is true for a typed 37', () => {
    expect(partEdited(PART, original, { dv: { ...FIFTY, value: 37 } }, [term])).toBe(true);
  });
});

describe('baselineAfter', () => {
  const was = { dv: { field: 'f.dv', value: 50 }, opt: { field: 'f.o', value: 1 } };
  const redrafted = (criteria: Record<string, unknown>) => answer({ document: { criteria } });

  it('takes the redrafted part rows from the new answer and every other row as first shown', () => {
    const next = redrafted({
      dv: { field: 'f.dv', value: 10 }, // the trader had edited this one (other part)
      opt: { field: 'f.o', value: 2 }, // the redrafted part
      fresh: { field: 'f.n' },
    });
    const baseline = baselineAfter(was, next, { ...PART, criteria: ['opt'] });
    expect(baseline).toEqual({
      dv: { field: 'f.dv', value: 50 },
      opt: { field: 'f.o', value: 2 },
      fresh: { field: 'f.n' },
    });
  });

  it('keeps an edit of another part visible against the new answer', () => {
    const next = redrafted({ dv: { field: 'f.dv', value: 10 }, opt: { field: 'f.o', value: 2 } });
    const baseline = baselineAfter(was, next, { ...PART, criteria: ['opt'] });
    const other = { ...PART, id: 'p2', criteria: ['dv'], unresolved: [] };
    expect(partEdited(other, baseline, next.document['criteria'], undefined)).toBe(true);
    const redone = { ...PART, criteria: ['opt'], unresolved: [] };
    expect(partEdited(redone, baseline, next.document['criteria'], undefined)).toBe(false);
  });

  it('is the new answer rows when the old baseline is unknown', () => {
    const next = redrafted({ a: { field: 'f.a' } });
    expect(baselineAfter(undefined, next, PART)).toEqual({ a: { field: 'f.a' } });
  });
});
