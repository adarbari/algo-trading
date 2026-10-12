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

  it('is null when the row was removed or the index is out of range', () => {
    expect(readingSwap({ id: 'mine', criteria: {} }, LIQUID, 0, 1)).toBeNull();
    expect(readingSwap(doc(), LIQUID, 0, 7)).toBeNull();
    expect(readingSwap(doc(), LIQUID, 5, 1)).toBeNull();
  });
});
