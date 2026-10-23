import { describe, expect, it } from 'vitest';

import type { CatalogueFeature } from '../model/catalogue';
import { columnOptions, fieldOptions } from './options';

const feature = (patch: Partial<CatalogueFeature>): CatalogueFeature => ({
  name: 'feature.market_cap',
  kind: 'expression',
  source: 'expression',
  dtype: 'float',
  format: 'COMPACT',
  description: 'shares_outstanding x close',
  nullMeaning: '',
  version: null,
  group: null,
  key: null,
  inputs: [],
  unit: 'usd',
  range: null,
  categories: [],
  scope: 'site',
  owner: null,
  licence: 'open',
  guide: null,
  ...patch,
});

describe('column options', () => {
  it('describes each feature with its unit and kind, skipping chosen and identity fields', () => {
    const catalogue = [
      feature({}),
      feature({
        name: 'instrument.symbol',
        kind: 'instrument',
        unit: null,
        description: 'reference fact',
      }),
      feature({
        name: 'rollup.iv30@v1.iv30',
        kind: 'chain',
        unit: 'decimal',
        group: 'iv30@v1',
        description: 'Our IV30',
      }),
      feature({
        name: 'feature.my_ratio',
        scope: 'user',
        owner: 'bob',
        unit: 'ratio',
        description: 'Mine',
        licence: 'personal',
      }),
    ];
    expect(columnOptions(catalogue, ['rollup.iv30@v1.iv30'])).toEqual([
      {
        value: 'feature.market_cap',
        label: 'feature.market_cap',
        description: 'Market cap: shares_outstanding x close ($ · expression)',
        badge: 'expression',
        group: 'Expression features',
      },
      {
        value: 'feature.my_ratio',
        label: 'feature.my_ratio',
        description: 'My ratio: Mine (ratio · expression)',
        badge: 'expression · yours · personal licence',
        group: 'Your features',
      },
    ]);
  });
});

describe('field options', () => {
  const CATALOGUE = [
    feature({
      name: 'rollup.iv30@v1.iv30',
      description: 'Our 30-day IV',
      unit: 'decimal',
      group: 'iv30@v1',
      licence: 'personal',
    }),
    feature({
      name: 'feature.vol_gap',
      description: 'IV minus HV',
      unit: 'ratio',
      scope: 'user',
    }),
  ];

  it("describes a field by its guide's one-line summary when it has one", () => {
    const guided = {
      ...CATALOGUE[0],
      guide: { summary: 'The 30-day at-the-money implied volatility.' },
    } as CatalogueFeature;
    expect(fieldOptions([guided])[0]?.description).toBe(
      'The 30-day at-the-money implied volatility. · fraction (shown as %) · personal licence',
    );
  });

  it('describes each feature with its unit and licence, and badges formulas', () => {
    const [iv, own] = fieldOptions(CATALOGUE);
    expect(iv).toMatchObject({ value: 'rollup.iv30@v1.iv30', group: 'iv30@v1' });
    expect(iv?.description).toBe('Our 30-day IV · fraction (shown as %) · personal licence');
    expect(own).toMatchObject({ badge: 'yours', group: 'Your features' });
  });
});
