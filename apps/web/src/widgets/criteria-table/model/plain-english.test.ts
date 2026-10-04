import { describe, expect, it } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';
import type { Criterion } from '@/entities/screen';

import { plainEnglish } from './plain-english';

const catalogue = [
  { name: 'rollup.iv30@v1.iv30', dtype: 'float32', unit: 'decimal' },
  { name: 'rollup.price_stats@v2.close', dtype: 'float', unit: 'usd_per_share' },
] as CatalogueFeature[];

const criterion = (c: Partial<Criterion> & { id: string }): Criterion => ({
  field: 'rollup.iv30@v1.iv30',
  op: 'gte',
  mode: 'hard',
  value: 0.5,
  ...c,
});

describe('plainEnglish', () => {
  it('reads each mode and types a fraction as a percent', () => {
    const text = plainEnglish(
      [
        criterion({ id: 'iv' }),
        criterion({
          id: 'px',
          field: 'rollup.price_stats@v2.close',
          op: 'gt',
          value: 5,
          mode: 'soft',
          tolerance: 1,
        }),
        criterion({ id: 'iv2', mode: 'score', value: 0.4 }),
      ],
      catalogue,
      'liquid_optionable',
    );
    expect(text).toBe(
      'Find instruments in liquid_optionable where IV30 ≥ 50%. A near miss on Close > $5 is tolerated and flagged. Prefer IV30 ≥ 40%; missing these only lowers the score.',
    );
  });

  it('reads a criterion once when its preset label already states the condition', () => {
    const text = plainEnglish(
      [
        criterion({ id: 'iv', label: 'IV30 >= 50%' }),
        criterion({
          id: 'px',
          field: 'rollup.price_stats@v2.close',
          op: 'gt',
          value: 5,
          label: 'Price > $5',
        }),
        criterion({
          id: 'adv',
          field: 'rollup.price_stats@v2.close',
          value: 50_000_000,
          label: 'Stock ADV > $50M',
        }),
        criterion({ id: 'named', value: 0.3, label: 'Implied vol' }),
      ],
      catalogue,
      null,
    );
    expect(text).toBe(
      'Find instruments where IV30 >= 50%, Price > $5, Stock ADV > $50M and Implied vol ≥ 30%.',
    );
  });

  it('writes large dollar amounts compactly', () => {
    const adv = criterion({
      id: 'adv',
      field: 'rollup.price_stats@v2.close',
      op: 'gte',
      value: 50_000_000,
    });
    expect(plainEnglish([adv], catalogue, null)).toBe('Find instruments where Close ≥ $50M.');
  });

  it('says nothing until a criterion is complete', () => {
    expect(plainEnglish([criterion({ id: 'a', field: '' })], catalogue, null)).toBeNull();
    expect(
      plainEnglish(
        [criterion({ id: 'a', op: 'gte' }), { id: 'b', field: 'x', op: 'gte', mode: 'hard' }],
        catalogue,
        null,
      ),
    ).toContain('IV30');
  });
});
