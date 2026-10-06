import { describe, expect, it } from 'vitest';

import { regimeFixture, unknownRegimeFixture } from './fixtures';
import {
  changedIndicators,
  episodeName,
  indicatorChange,
  indicatorsOfPace,
  indicatorStatus,
  plainLabel,
  readingList,
  regimeLabelFeature,
  regimeTone,
  gateLine,
  gatePauses,
  sizingLine,
  storedLabel,
  toChartBands,
  type RegimeBand,
  type RegimeEpisode,
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
  it('says the size in force and who pauses where, from what the server sent', () => {
    expect(sizingLine(regimeFixture())).toBe(
      'New positions sized at 75% in Clouds building; Momentum pauses in Severe storm; VRP scanner pauses in Storm and Severe storm',
    );
  });

  it('says the unknown size while the regime is not computed', () => {
    expect(sizingLine(unknownRegimeFixture())).toBe(
      'New positions sized at 0% (regime not computed); Momentum pauses in Severe storm; VRP scanner pauses in Storm and Severe storm',
    );
  });

  it('says the gate is off, and names no pause, when it is', () => {
    const base = regimeFixture().sizing;
    expect(sizingLine(regimeFixture({ sizing: { ...base, enabled: false } }))).toBe(
      'New positions at full size (the regime gate is off)',
    );
  });

  it('leaves out a screener whose gate is off or that pauses nowhere', () => {
    const base = regimeFixture().sizing;
    const sizing = {
      ...base,
      screeners: [
        { screenerId: 'a', name: 'A', enabled: false, pauseIn: ['STRESS'] as const },
        { screenerId: 'b', name: 'B', enabled: true, pauseIn: [] },
      ],
    };
    expect(sizingLine(regimeFixture({ sizing }))).toBe(
      'New positions sized at 75% in Clouds building',
    );
  });
});

describe('gateLine', () => {
  const { sizing } = regimeFixture();

  it('lists the labels the screen pauses in', () => {
    expect(gateLine(sizing, 'vrp_scanner')).toBe('This screen pauses in Storm and Severe storm');
    expect(gateLine(sizing, 'momentum')).toBe('This screen pauses in Severe storm');
  });

  it('says there is no gate for a screen that pauses nowhere or is not saved yet', () => {
    expect(gateLine(sizing, 'quiet')).toBe('No regime gate');
    expect(gateLine(sizing, 'unsaved')).toBe('No regime gate');
    expect(
      gateLine(
        {
          ...sizing,
          screeners: [
            {
              screenerId: 'vrp_scanner',
              name: 'VRP',
              enabled: false,
              pauseIn: ['STRESS'] as const,
            },
          ],
        },
        'vrp_scanner',
      ),
    ).toBe('No regime gate');
  });
});

describe('storedLabel', () => {
  it('accepts the four labels and nothing else', () => {
    expect(storedLabel('STRESS')).toBe('STRESS');
    expect(storedLabel('UNKNOWN')).toBeNull();
    expect(storedLabel('SUNNY')).toBeNull();
    expect(storedLabel(null)).toBeNull();
    expect(storedLabel(undefined)).toBeNull();
  });
});

describe('gatePauses', () => {
  it('says what a screener does in words, and what a gate that is off is set to', () => {
    const gate = { screenerId: 'a', name: 'A', enabled: true, pauseIn: ['STRESS'] as const };
    expect(gatePauses(gate)).toBe('Pauses in Storm');
    expect(gatePauses({ ...gate, pauseIn: [] })).toBe('Never pauses');
    expect(gatePauses({ ...gate, enabled: false })).toBe('Gate off (set to pause in Storm)');
    expect(gatePauses({ ...gate, enabled: false, pauseIn: [] })).toBe('Gate off');
  });
});

describe('episodeName', () => {
  const episodes = [
    { key: 'tariffs_2025', name: 'Tariff shock, spring 2025' },
  ] as unknown as readonly RegimeEpisode[];

  it('is the name the API gives the episode', () => {
    expect(episodeName(episodes, 'tariffs_2025')).toBe('Tariff shock, spring 2025');
  });

  it('spaces the key of an episode the API does not name', () => {
    expect(episodeName(episodes, 'crash_1987')).toBe('crash 1987');
    expect(episodeName([], 'tariffs_2025')).toBe('tariffs 2025');
  });
});

describe('regimeLabelFeature', () => {
  it('names the label field in the group of the scores', () => {
    expect(regimeLabelFeature(regimeFixture())).toBe('market.regime@v3.label');
  });
});
