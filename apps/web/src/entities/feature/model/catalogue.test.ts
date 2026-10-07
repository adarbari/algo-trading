import { describe, expect, it } from 'vitest';

import {
  displayValue,
  featureFormat,
  featureGroup,
  featureMarks,
  featureLabel,
  featureTitle,
  isNumericFeature,
  isOwn,
  isPersonal,
  unitLabel,
  type CatalogueFeature,
} from './catalogue';
import { distributionBins, distributionCategories, distributionMarkers } from './distribution';

const feature = (patch: Partial<CatalogueFeature>): CatalogueFeature => ({
  name: 'rollup.iv30@v1.iv30',
  kind: 'chain',
  source: 'rollups/instrument/iv30@v1',
  dtype: 'float',
  format: 'PERCENT',
  description: 'Our 30-day ATM implied volatility',
  nullMeaning: 'no chain',
  version: 1,
  group: 'iv30@v1',
  key: 'iv30.iv30@v1',
  inputs: [],
  unit: 'decimal',
  range: null,
  categories: [],
  scope: 'site',
  owner: null,
  licence: 'open',
  guide: null,
  ...patch,
});

describe('feature catalogue', () => {
  it('formats values by unit, then dtype', () => {
    expect(featureFormat(feature({}))).toEqual({ kind: 'percent' });
    expect(featureFormat(feature({ unit: 'usd' }))).toEqual({ kind: 'currency-compact' });
    expect(featureFormat(feature({ unit: 'usd_per_share' }))).toEqual({ kind: 'currency' });
    expect(featureFormat(feature({ unit: 'date', dtype: 'date' }))).toEqual({ kind: 'date' });
    expect(featureFormat(feature({ unit: null, dtype: 'int' }))).toEqual({ kind: 'number' });
    expect(featureFormat(feature({ unit: 'category', dtype: 'str' }))).toEqual({ kind: 'text' });
    expect(featureFormat(undefined)).toEqual({ kind: 'text' });
  });

  it('labels features briefly for headers and fully for rows', () => {
    expect(featureLabel('rollup.iv30@v1.iv30')).toBe('IV30');
    expect(featureLabel('rollup.price_stats@v2.sma_200')).toBe('Sma 200');
    expect(featureTitle('feature.market_cap')).toBe('Market cap');
    expect(featureTitle('instrument.sector')).toBe('Sector');
  });

  it("groups and marks the user's own and personal-licence features", () => {
    const mine = feature({ scope: 'user', owner: 'bob', group: null, name: 'feature.my_ratio' });
    expect(isOwn(mine)).toBe(true);
    expect(isPersonal(mine)).toBe(false);
    const ibkr = feature({ licence: 'personal' });
    expect(isPersonal(ibkr)).toBe(true);
    expect(featureMarks({ ...mine, licence: 'personal' })).toEqual(['yours', 'personal licence']);
    expect(featureMarks(feature({}))).toEqual([]);
    expect(featureGroup(mine)).toBe('Your features');
    expect(featureGroup(feature({}))).toBe('iv30@v1');
    expect(featureGroup(feature({ group: null, name: 'instrument.sector' }))).toBe('Instrument');
    expect(isNumericFeature(feature({ dtype: 'float32' }))).toBe(true);
    expect(isNumericFeature(feature({ dtype: 'str' }))).toBe(false);
  });

  it('shows booleans in words and units in plain English', () => {
    expect(displayValue(true)).toBe('Yes');
    expect(displayValue(false)).toBe('No');
    expect(displayValue(3)).toBe(3);
    expect(unitLabel('usd_per_share')).toBe('$ / share');
    expect(unitLabel('sessions')).toBe('sessions');
    expect(unitLabel(null)).toBe('');
  });
});

describe('feature distribution', () => {
  const distribution = {
    name: 'rollup.iv30@v1.iv30',
    session: '2026-10-02',
    count: 10,
    nulls: 1,
    quantiles: [
      { q: 0.25, value: 0.3 },
      { q: 0.5, value: 0.45 },
      { q: 0.75, value: 0.7 },
      { q: 0.99, value: 1.6 },
    ],
    histogram: [
      { lo: 0, hi: 0.5, count: 6 },
      { lo: 0.5, hi: 1, count: 3 },
    ],
    categories: [],
    unknown: null,
    passing: [{ intent: 'a squeeze', count: 6, bins: [5, 1] }],
  };

  it('maps bins and quartile markers, with the ticker highlighted', () => {
    expect(distributionBins(distribution)).toEqual([
      { start: 0, end: 0.5, count: 6 },
      { start: 0.5, end: 1, count: 3 },
    ]);
    expect(distributionMarkers(distribution, { label: 'AAPL', value: 0.24 })).toEqual([
      { value: 0.3, label: 'p25' },
      { value: 0.45, label: 'median' },
      { value: 0.7, label: 'p75' },
      { value: 0.24, label: 'AAPL', tone: 'accent' },
    ]);
  });

  it("carries each bin's passing count when a criterion is chosen", () => {
    expect(distributionBins(distribution, distribution.passing[0])).toEqual([
      { start: 0, end: 0.5, count: 6, highlighted: 5 },
      { start: 0.5, end: 1, count: 3, highlighted: 1 },
    ]);
  });

  it('lists category values', () => {
    expect(
      distributionCategories({ ...distribution, categories: [{ value: 'Technology', count: 3 }] }),
    ).toEqual(['Technology']);
    expect(distributionCategories(undefined)).toEqual([]);
  });
});
