import { describe, expect, it } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';

import { featureOptions } from './options';

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

describe('feature options', () => {
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
    expect(featureOptions(catalogue, ['rollup.iv30@v1.iv30'])).toEqual([
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
