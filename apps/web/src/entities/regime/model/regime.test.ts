import { describe, expect, it } from 'vitest';

import { regimeFixture } from './fixtures';
import {
  changedIndicators,
  indicatorChange,
  indicatorsOfPace,
  indicatorStatus,
  plainLabel,
  readingList,
  regimeTone,
  sizingLine,
  toChartBands,
  type RegimeBand,
  type RegimeLabel,
} from './regime';

const LABELS: RegimeLabel[] = ['CALM', 'CAUTION', 'STRESS', 'CRISIS', 'UNKNOWN'];

describe('plainLabel and regimeTone', () => {
  it('names each regime as weather', () => {
    expect(LABELS.map(plainLabel)).toEqual([
      'Clear',
      'Clouds building',
      'Storm',
      'Severe storm',
      'Not computed',
    ]);
  });

  it('tints CALM positive, CAUTION warning, STRESS and CRISIS negative, UNKNOWN neutral', () => {
    expect(LABELS.map(regimeTone)).toEqual([
      'positive',
      'warning',
      'negative',
      'negative',
      'neutral',
    ]);
  });
});

describe('toChartBands', () => {
  const bands: RegimeBand[] = [
    { start: '2026-01-02', end: '2026-02-27', label: 'CALM' },
    { start: '2026-03-02', end: '2026-03-13', label: 'CAUTION' },
    { start: '2026-03-16', end: '2026-03-20', label: 'STRESS' },
    { start: '2026-03-23', end: '2026-03-27', label: 'CRISIS' },
    { start: '2026-03-30', end: '2026-04-03', label: 'UNKNOWN' },
  ];

  it('tints and names each band, oldest first, and draws nothing for UNKNOWN', () => {
    expect(toChartBands(bands)).toEqual([
      { start: '2026-01-02', end: '2026-02-27', tone: 'positive', label: 'Clear' },
      { start: '2026-03-02', end: '2026-03-13', tone: 'warning', label: 'Clouds building' },
      { start: '2026-03-16', end: '2026-03-20', tone: 'negative', label: 'Storm' },
      { start: '2026-03-23', end: '2026-03-27', tone: 'negative', label: 'Severe storm' },
    ]);
  });

  it('keeps only the floor label and worse (the price chart shades Storm and worse)', () => {
    expect(toChartBands(bands, 'STRESS').map((b) => b.label)).toEqual(['Storm', 'Severe storm']);
  });

  it('is empty for no bands', () => {
    expect(toChartBands([])).toEqual([]);
  });
});

describe('indicators', () => {
  const regime = regimeFixture();

  it('splits the cards by pace and keeps the server order', () => {
    expect(indicatorsOfPace(regime, 'slow').map((i) => i.key)).toEqual(['curve_10y3m', 'nfci']);
    expect(indicatorsOfPace(regime, 'fast').map((i) => i.key)).toEqual(['vix_term']);
  });

  it('lists the ones whose verdict changed', () => {
    expect(changedIndicators(regime).map((i) => i.key)).toEqual(['nfci']);
  });

  it('marks a change by the verdict it ended on, and says nothing when unchanged or unstored', () => {
    const [curve, nfci, vix] = regime.indicators;
    expect(nfci && indicatorChange(nfci)).toEqual({ change: 'up', label: 'Turned on this week' });
    expect(curve && indicatorChange(curve)).toBeUndefined();
    expect(vix && indicatorChange({ ...vix, changed: null })).toBeUndefined();
    expect(vix && indicatorChange({ ...vix, changed: true, status: 'OFF' })?.change).toBe('down');
    expect(vix && indicatorChange({ ...vix, changed: true, status: 'UNKNOWN' })?.change).toBe(
      'new',
    );
  });

  it('words each verdict', () => {
    expect(indicatorStatus('ON')).toEqual({ tone: 'warning', label: 'On' });
    expect(indicatorStatus('OFF')).toEqual({ tone: 'positive', label: 'Off' });
    expect(indicatorStatus('UNKNOWN')).toEqual({ tone: 'neutral', label: 'Unknown' });
  });
});

describe('readingList', () => {
  it('lists each link once, with every card that cites it', () => {
    const list = readingList(regimeFixture());
    expect(list.map((l) => l.url)).toEqual([
      'https://fred.stlouisfed.org/series/T10Y3M',
      'https://www.chicagofed.org/nfci',
    ]);
    expect(list[0]?.cards).toEqual(['Is the yield curve inverted?']);
    expect(list[1]?.cards).toEqual(['Are financial conditions tight?', 'Is fear rising?']);
  });
});

describe('sizingLine', () => {
  it('says 100% and that the regime is not computed while it is UNKNOWN', () => {
    expect(sizingLine(regimeFixture({ sizing: { label: 'UNKNOWN', multiplier: null } }))).toBe(
      'New positions sized at 100% (regime not computed)',
    );
  });

  it('says the multiplier in force for a known label', () => {
    expect(sizingLine(regimeFixture({ sizing: { label: 'CAUTION', multiplier: 0.75 } }))).toBe(
      'New positions sized at 75% (clouds building)',
    );
  });
});
