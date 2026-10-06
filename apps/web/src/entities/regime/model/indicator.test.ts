import { describe, expect, it } from 'vitest';

import { regimeFixture } from './fixtures';
import {
  indicatorFormat,
  meterDirection,
  meterThresholds,
  onWhenLine,
  provenanceLine,
  sourceItems,
} from './indicator';
import type { IndicatorSource, RegimeIndicator } from './regime';

const [curve, nfci, vix] = regimeFixture().indicators as [
  RegimeIndicator,
  RegimeIndicator,
  RegimeIndicator,
];

describe('the meter', () => {
  it('takes its direction from the card and marks one threshold where it turns on', () => {
    expect(meterDirection(curve)).toBe('lower-is-risk');
    expect(meterDirection(nfci)).toBe('higher-is-risk');
    expect(meterThresholds(nfci)).toEqual([{ at: 0.5, label: 'on', tone: 'warning' }]);
  });

  it('has no threshold and reads the high side as risk when the card has no rule', () => {
    const none = { ...vix, threshold: null, direction: null };
    expect(meterThresholds(none)).toEqual([]);
    expect(meterDirection(none)).toBe('higher-is-risk');
    expect(onWhenLine(none, { kind: 'number' })).toBeUndefined();
  });

  it('says when it is on from the direction', () => {
    expect(onWhenLine(curve, indicatorFormat(curve))).toBe('On when below 0.00');
    expect(onWhenLine(nfci, indicatorFormat(nfci))).toBe('On when above 0.50');
  });
});

describe('indicatorFormat', () => {
  it('reads a number with two decimals, whole numbers on a wide range, NUMBER when not catalogued', () => {
    expect(indicatorFormat(curve)).toEqual({ kind: 'number', digits: 2 });
    expect(indicatorFormat({ ...curve, range: { min: 0, max: 800 } })).toEqual({
      kind: 'number',
      digits: 0,
    });
    expect(indicatorFormat({ ...curve, format: null })).toEqual({ kind: 'number', digits: 2 });
    expect(indicatorFormat({ ...curve, format: 'PERCENT' })).toEqual({ kind: 'percent' });
  });
});

describe('sourceItems', () => {
  it('lists the source in use first and marks the others as not used today', () => {
    const [active, other] = nfci.sources as [IndicatorSource, IndicatorSource];
    const { linked, unlinked } = sourceItems({ ...nfci, sources: [other, active] });
    expect(linked).toEqual([
      { label: 'FRED NFCI', cadence: 'weekly', url: 'https://fred.stlouisfed.org/series/NFCI' },
      {
        label: 'FRED ANFCI',
        cadence: 'weekly, not used today',
        url: 'https://fred.stlouisfed.org/series/ANFCI',
      },
    ]);
    expect(unlinked).toEqual([]);
  });

  it('names a source with no page of its own in text', () => {
    const source = { ...(nfci.sources[0] as IndicatorSource), url: null, label: 'SPY bars' };
    expect(sourceItems({ ...nfci, sources: [source] })).toEqual({
      linked: [],
      unlinked: ['SPY bars · weekly'],
    });
  });
});

describe('provenanceLine', () => {
  const [active, other] = nfci.sources as [IndicatorSource, IndicatorSource];

  it('gives the last observation, its release and, for a revised series, the first vintage', () => {
    expect(provenanceLine(active)).toMatch(
      /^FRED NFCI: last observation .*, released .*; before .* values are today's revised figures$/,
    );
  });

  it('leaves out the revision note for an unrevised series', () => {
    const line = provenanceLine({ ...active, firstVintage: null });
    expect(line).toMatch(/^FRED NFCI: last observation .*, released [^;]*$/);
  });

  it('says nothing for an unused source or one with no observation', () => {
    expect(provenanceLine(other)).toBeNull();
    expect(provenanceLine({ ...active, lastObservation: null })).toBeNull();
  });
});
