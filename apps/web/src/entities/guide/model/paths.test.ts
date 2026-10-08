import { describe, expect, it } from 'vitest';

import {
  BUILT_SECTIONS,
  episodePath,
  exploreFieldPath,
  fieldPath,
  fieldsPath,
  indicatorPath,
  parseFieldsSearch,
  playbookPath,
  screenerBuilderPath,
  screenerResultsPath,
  situationPath,
  themeTitle,
} from './paths';

describe('guide paths', () => {
  it('builds the playbook, situation and screener paths, encoding what is in them', () => {
    expect(playbookPath('breakout')).toBe('/guide/playbooks/breakout');
    expect(situationPath('earnings-gap')).toBe('/guide/situations/earnings-gap');
    expect(screenerResultsPath('my screen')).toBe('/screeners/my%20screen');
    expect(screenerBuilderPath('breakout')).toBe('/screeners/breakout/edit');
  });

  it('builds the regime indicator and market fall paths', () => {
    expect(indicatorPath('curve_10y3m')).toBe('/guide/regime/indicators/curve_10y3m');
    expect(episodePath('gfc_2007')).toBe('/guide/regime/episodes/gfc_2007');
  });

  it('has pages for the market regime, playbooks, fields and situations, in the Guide’s order', () => {
    expect(BUILT_SECTIONS).toEqual(['regime', 'playbooks', 'fields', 'situations']);
  });

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

  it('capitalises a theme for a heading', () => {
    expect(themeTitle('momentum and trend')).toBe('Momentum and trend');
  });
});
