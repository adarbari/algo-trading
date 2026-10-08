import { describe, expect, it } from 'vitest';

import {
  BUILT_SECTIONS,
  episodePath,
  exploreFieldPath,
  fieldPath,
  fieldsPath,
  guideEntryPath,
  indicatorPath,
  parseFieldsSearch,
  playbookPath,
  screenerBuilderPath,
  screenerResultsPath,
  situationPath,
  startPath,
  termPath,
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

  it('has pages for every section, Start here first and the Glossary last', () => {
    expect(BUILT_SECTIONS).toEqual([
      'start',
      'regime',
      'playbooks',
      'fields',
      'situations',
      'glossary',
    ]);
  });

  it('builds the Start here and glossary paths', () => {
    expect(startPath('read_a_result')).toBe('/guide/start/read_a_result');
    expect(termPath('not_run')).toBe('/guide/glossary/not_run');
  });

  it('resolves an entry by the kind and id the server gives, else the home', () => {
    expect(guideEntryPath('start', 'how_the_app_thinks')).toBe('/guide/start/how_the_app_thinks');
    expect(guideEntryPath('term', 'session')).toBe('/guide/glossary/session');
    expect(guideEntryPath('field', 'a@v1.b')).toBe('/guide/fields/a%40v1.b');
    expect(guideEntryPath('playbook', 'breakout')).toBe('/guide/playbooks/breakout');
    expect(guideEntryPath('situation', 'earnings-gap')).toBe('/guide/situations/earnings-gap');
    expect(guideEntryPath('indicator', 'k')).toBe('/guide/regime/indicators/k');
    expect(guideEntryPath('episode', 'gfc')).toBe('/guide/regime/episodes/gfc');
    expect(guideEntryPath('other', 'x')).toBe('/guide');
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
