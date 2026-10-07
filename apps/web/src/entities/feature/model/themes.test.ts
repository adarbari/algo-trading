import { describe, expect, it } from 'vitest';

import type { CatalogueFeature } from './catalogue';
import {
  guideThemes,
  OTHER_THEME,
  resolveSelection,
  searchFields,
  shortMeaning,
  themeFields,
  themeOf,
} from './themes';

const field = (
  name: string,
  theme: string | null,
  reads = '',
  description = '',
): CatalogueFeature =>
  ({
    name,
    description,
    guide: theme === null ? null : { theme, reads, uses: [], caveats: [], sources: [] },
  }) as unknown as CatalogueFeature;

const catalogue = [
  field('instrument.symbol', null, '', 'The ticker'),
  field(
    'rollup.bands@v2.bb_squeeze',
    'Volatility',
    'Bands inside the channel. A squeeze is quiet.',
  ),
  field('rollup.momentum@v1.rsi_14', 'Momentum and trend', 'Relative strength, 0 to 100.'),
  field('rollup.bands@v2.bb_width', 'Volatility', 'Band width.'),
  field('feature.other', null, '', 'Something else'),
];

describe('guide themes', () => {
  it('lists themes in order of first appearance with their counts, Other last', () => {
    expect(guideThemes(catalogue)).toEqual([
      { name: 'Volatility', count: 2 },
      { name: 'Momentum and trend', count: 1 },
      { name: OTHER_THEME, count: 2 },
    ]);
    expect(themeOf(catalogue[0] as CatalogueFeature)).toBe(OTHER_THEME);
    expect(guideThemes([])).toEqual([]);
  });

  it('lists the fields of a theme in catalogue order', () => {
    expect(themeFields(catalogue, 'Volatility').map((f) => f.name)).toEqual([
      'rollup.bands@v2.bb_squeeze',
      'rollup.bands@v2.bb_width',
    ]);
  });
});

describe('searching fields', () => {
  it('matches every word against names, titles, descriptions and the guide text', () => {
    expect(searchFields(catalogue, 'squeeze').map((f) => f.name)).toEqual([
      'rollup.bands@v2.bb_squeeze',
    ]);
    expect(searchFields(catalogue, 'QUIET bands').map((f) => f.name)).toEqual([
      'rollup.bands@v2.bb_squeeze',
    ]);
    expect(searchFields(catalogue, 'ticker').map((f) => f.name)).toEqual(['instrument.symbol']);
    expect(searchFields(catalogue, 'nothing like this')).toEqual([]);
  });

  it('keeps every field for an empty query', () => {
    expect(searchFields(catalogue, '  ')).toHaveLength(5);
  });
});

describe('a field in one line', () => {
  it('is the first sentence of the guide, else of the definition', () => {
    expect(shortMeaning(catalogue[1] as CatalogueFeature)).toBe('Bands inside the channel.');
    expect(shortMeaning(catalogue[0] as CatalogueFeature)).toBe('The ticker');
  });

  it('is cut at a long sentence', () => {
    const long = field('x', null, '', `${'word '.repeat(60)}end.`);
    expect(shortMeaning(long).length).toBeLessThanOrEqual(140);
    expect(shortMeaning(long).endsWith('…')).toBe(true);
  });
});

describe('the selection a link asks for', () => {
  it('lets a known field decide its theme', () => {
    const picked = resolveSelection(catalogue, {
      theme: 'Momentum and trend',
      field: 'rollup.bands@v2.bb_width',
    });
    expect(picked?.theme).toBe('Volatility');
    expect(picked?.field?.name).toBe('rollup.bands@v2.bb_width');
  });

  it('takes the theme with its first field, else the first theme', () => {
    expect(resolveSelection(catalogue, { theme: 'Momentum and trend' })?.field?.name).toBe(
      'rollup.momentum@v1.rsi_14',
    );
    expect(resolveSelection(catalogue, { theme: 'Nope', field: 'nope' })?.theme).toBe('Volatility');
    expect(resolveSelection(catalogue, {})?.field?.name).toBe('rollup.bands@v2.bb_squeeze');
  });

  it('has nothing to select in an empty catalogue', () => {
    expect(resolveSelection([], {})).toBeNull();
  });
});
