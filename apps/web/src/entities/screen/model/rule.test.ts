import { describe, expect, it } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';

import { describeCriterion, describeRule } from './rule';

const feature = (dtype: string, unit: string | null = null): CatalogueFeature =>
  ({ dtype, unit, categories: [] }) as unknown as CatalogueFeature;

describe('describeCriterion', () => {
  it('reads a fraction as a percent and follows the threshold when it changes', () => {
    const iv30 = feature('float32', 'decimal');
    const field = 'feature.vrp_iv30';
    expect(describeCriterion({ field, op: 'gte', value: 0.5 }, iv30)).toBe('IV30 ≥ 50%');
    expect(describeCriterion({ field, op: 'gt', value: 1.5 }, iv30)).toBe('IV30 > 150%');
  });

  it('shows the unit prefix, suffix and thousands', () => {
    const field = 'rollup.price_stats@v2.adv_usd_20d';
    expect(
      describeCriterion({ field, op: 'gte', value: 50_000_000 }, feature('float32', 'usd')),
    ).toBe('Avg dollar volume 20d ≥ $50,000,000');
    expect(
      describeCriterion(
        { field: 'feature.iv_hv_spread', op: 'gte', value: 10 },
        feature('float32', 'pct_points'),
      ),
    ).toBe('IV − HV ≥ 10 pts');
    expect(
      describeCriterion(
        { field: 'feature.vrp_iv_hv_ratio', op: 'gte', value: 1.25 },
        feature('float32', 'ratio'),
      ),
    ).toBe('IV30 / HV30 ≥ 1.25×');
  });

  it('reads lists, ranges and empty checks', () => {
    const text = feature('str');
    expect(
      describeCriterion({ field: 'feature.near_52w', op: 'in', value: ['HIGH', 'LOW'] }, text),
    ).toBe('Near 52w in HIGH, LOW');
    expect(
      describeCriterion(
        { field: 'rollup.price_stats@v2.close', op: 'between', value: [5, 10] },
        feature('float32'),
      ),
    ).toBe('Last close between 5 and 10');
    expect(describeCriterion({ field: 'instrument.sector', op: 'not_null' }, text)).toBe(
      'Sector has a value',
    );
  });

  it('names just the field while the threshold is not set', () => {
    expect(describeCriterion({ field: 'rollup.price_stats@v2.close', op: 'gte' }, undefined)).toBe(
      'Last close',
    );
  });
});

describe('describeRule', () => {
  it('is the rule without the field name, in the field unit', () => {
    const iv30 = feature('float32', 'decimal');
    expect(describeRule({ field: 'f', op: 'gte', value: 0.5 }, iv30)).toBe('≥ 50%');
    expect(describeRule({ field: 'f', op: 'not_null' }, undefined)).toBe('has a value');
    expect(describeRule({ field: 'f', op: 'gte' }, iv30)).toBe('');
  });
});
