import { describe, expect, it } from 'vitest';

import {
  BUILT_SECTIONS,
  exploreFieldPath,
  fieldPath,
  fieldsPath,
  parseFieldsSearch,
  themeTitle,
} from './paths';

describe('guide paths', () => {
  it('encodes a catalogue name in a field path', () => {
    expect(fieldPath('rollup.momentum@v1.rel_volume')).toBe(
      '/guide/fields/rollup.momentum%40v1.rel_volume',
    );
  });

  it('builds the field index path with only the choices given', () => {
    expect(fieldsPath()).toBe('/guide/fields');
    expect(fieldsPath({ theme: 'price levels' })).toBe('/guide/fields?theme=price+levels');
    expect(fieldsPath({ view: 'intent', intent: 'A squeeze' })).toBe(
      '/guide/fields?view=intent&intent=A+squeeze',
    );
  });

  it('opens Explore on the Features tab with the ticker and the field', () => {
    const url = new URL(exploreFieldPath('feature.x', 'AAPL'), 'http://x');
    expect(url.pathname).toBe('/explore');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      sel: 'AAPL',
      focus: 'AAPL',
      tab: 'features',
      feature: 'feature.x',
    });
  });

  it('keeps only valid search params of the field index', () => {
    expect(parseFieldsSearch({ view: 'az', theme: ' volume ', intent: '', junk: 1 })).toEqual({
      view: 'az',
      theme: 'volume',
    });
    expect(parseFieldsSearch({ view: 'nope' })).toEqual({});
  });

  it('capitalises a theme for a heading, and ships only the Fields section today', () => {
    expect(themeTitle('momentum and trend')).toBe('Momentum and trend');
    expect(BUILT_SECTIONS).toEqual(['fields']);
  });
});
