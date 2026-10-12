import { describe, expect, it } from 'vitest';

import type { ScreenDocument } from '@/entities/screen';

import { readingSwap, rowOfReading, type Unresolved } from './readings';

const LIQUID: Unresolved = {
  term: 'liquid',
  span: 'liquid',
  default_index: 0,
  alternatives: [
    {
      text: 'over $50M traded a day',
      criterion: { field: 'f.dollar_volume', op: 'gte', value: 50_000_000, mode: 'hard' },
    },
    {
      text: 'over $10M traded a day',
      criterion: { field: 'f.dollar_volume', op: 'gte', value: 10_000_000, mode: 'hard' },
    },
    {
      text: 'in the top fifth by volume',
      criterion: { field: 'f.volume_rank', op: 'in', value: ['a', { b: 1, c: 2 }], mode: 'soft' },
    },
  ],
};

const doc = (extra: Record<string, Record<string, unknown>> = {}): ScreenDocument => ({
  id: 'mine',
  criteria: {
    price: { field: 'f.close', op: 'gte', value: 5, mode: 'hard' },
    dollar_volume: { ...LIQUID.alternatives[0]?.criterion },
    ...extra,
  },
});

describe('rowOfReading', () => {
  it('finds the row holding the default reading by equality, not by position', () => {
    expect(rowOfReading(doc(), LIQUID.alternatives[0]?.criterion ?? {})).toBe('dollar_volume');
  });

  it('matches nested values whatever their key order', () => {
    const reading = LIQUID.alternatives[2]?.criterion ?? {};
    const held = doc({
      vol: { field: 'f.volume_rank', op: 'in', value: ['a', { c: 2, b: 1 }], mode: 'soft' },
    });
    expect(rowOfReading(held, reading)).toBe('vol');
  });

  it('is null when more than one row holds it', () => {
    const twice = doc({ again: { ...LIQUID.alternatives[0]?.criterion } });
    expect(rowOfReading(twice, LIQUID.alternatives[0]?.criterion ?? {})).toBeNull();
    expect(readingSwap(twice, LIQUID, 0, 1)).toBeNull();
  });

  it('is null when no row holds it', () => {
    expect(rowOfReading(doc(), LIQUID.alternatives[1]?.criterion ?? {})).toBeNull();
  });
});

describe('readingSwap', () => {
  it('replaces the default reading by the picked one under the same row id', () => {
    expect(readingSwap(doc(), LIQUID, 0, 1)).toEqual({
      id: 'dollar_volume',
      field: 'f.dollar_volume',
      op: 'gte',
      value: 10_000_000,
      mode: 'hard',
    });
  });

  it('keeps what the row has that the readings lack (a near-miss rule, a mode)', () => {
    const held = doc();
    held.criteria = {
      ...held.criteria,
      dollar_volume: {
        ...LIQUID.alternatives[0]?.criterion,
        on_miss: 'warn',
        tolerance: { pct: 10 },
      },
    };
    const lean = {
      ...LIQUID,
      alternatives: LIQUID.alternatives.map((a) => ({
        text: a.text,
        criterion: {
          field: a.criterion['field'],
          op: a.criterion['op'],
          value: a.criterion['value'],
        },
      })),
    };
    held.criteria['dollar_volume'] = { ...held.criteria['dollar_volume'], mode: 'soft' };
    const swapped = readingSwap(held, lean, 0, 1);
    expect(swapped).toMatchObject({
      value: 10_000_000,
      mode: 'soft',
      on_miss: 'warn',
      tolerance: { pct: 10 },
    });
    // a key the new reading sets wins
    expect(readingSwap(doc(), LIQUID, 0, 2)).toMatchObject({ mode: 'soft', op: 'in' });
  });

  it('is null when the row was removed or the index is out of range', () => {
    expect(readingSwap({ id: 'mine', criteria: {} }, LIQUID, 0, 1)).toBeNull();
    expect(readingSwap(doc(), LIQUID, 0, 7)).toBeNull();
    expect(readingSwap(doc(), LIQUID, 5, 1)).toBeNull();
  });
});
