import { describe, expect, it } from 'vitest';

import {
  BAND_LABELS,
  episodeBands,
  evidenceLane,
  regimeLane,
  signalLane,
  toChartPoints,
  toHistoryChart,
  type SeriesHistory,
} from './history';
import type { Recession, RegimeEpisode } from './regime';

const history = (overrides: Partial<SeriesHistory> = {}): SeriesHistory => ({
  name: 'market.regime_indicators@v1.nfci',
  bucketSessions: 5,
  points: [],
  segments: [],
  ...overrides,
});

const episode = (overrides: Partial<RegimeEpisode> = {}): RegimeEpisode =>
  ({
    key: 'covid_2020',
    name: 'Covid crash, early 2020',
    peak: '2020-02-19',
    trough: '2020-03-23',
    recovered: '2020-08-18',
    ...overrides,
  }) as RegimeEpisode;

const window = { start: '2018-01-02', end: '2026-10-02' };

describe('toChartPoints', () => {
  it('keeps a gap as a null value so the line breaks, never a zero', () => {
    expect(
      toChartPoints(
        history({
          points: [
            { session: '2020-01-02', value: 0.1 },
            { session: '2020-01-09', value: null },
            { session: '2020-01-16', value: 0.3 },
          ],
        }),
      ),
    ).toEqual([
      { time: '2020-01-02', value: 0.1 },
      { time: '2020-01-09', value: null },
      { time: '2020-01-16', value: 0.3 },
    ]);
  });

  it('is empty without a history', () => {
    expect(toChartPoints(undefined)).toEqual([]);
  });
});

describe('signalLane', () => {
  const verdict = history({
    segments: [
      { start: '2019-01-02', end: '2019-06-28', value: 'OFF' },
      { start: '2019-07-01', end: '2019-12-31', value: 'ON' },
      { start: '2020-01-02', end: '2020-02-28', value: 'UNKNOWN' },
    ],
  });

  it('draws ON in warning and UNKNOWN in neutral and nothing for OFF', () => {
    expect(signalLane(verdict)?.segments).toEqual([
      { start: '2019-07-01', end: '2019-12-31', tone: 'warning', label: 'Signal on' },
      { start: '2020-01-02', end: '2020-02-28', tone: 'neutral', label: 'No data' },
    ]);
  });

  it('is no lane without a verdict history', () => {
    expect(signalLane(undefined)).toBeNull();
  });
});

describe('regimeLane', () => {
  it('names each run by its weather word and tints it by the label', () => {
    const lane = regimeLane(
      history({
        segments: [
          { start: '2019-01-02', end: '2019-03-29', value: 'CALM' },
          { start: '2019-04-01', end: '2019-04-30', value: 'CAUTION' },
          { start: '2019-05-01', end: '2019-05-31', value: 'STRESS' },
          { start: '2019-06-03', end: '2019-06-28', value: 'CRISIS' },
          { start: '2019-07-01', end: '2019-07-31', value: 'UNKNOWN' },
        ],
      }),
    );
    expect(lane?.segments.map((s) => [s.tone, s.label])).toEqual([
      ['positive', 'Clear'],
      ['warning', 'Clouds building'],
      ['negative', 'Storm'],
      ['negative', 'Severe storm'],
      ['neutral', 'Not computed'],
    ]);
  });
});

describe('evidenceLane', () => {
  const coverage = history({
    points: [
      { session: '2016-01-04', value: 0 },
      { session: '2016-06-01', value: null },
      { session: '2017-01-03', value: 0.5 },
      { session: '2017-06-01', value: 0.7 },
      { session: '2018-01-02', value: 0.9 },
      { session: '2018-06-01', value: 1 },
    ],
  });

  it('buckets coverage as none, partial and full, each run up to the day before the next', () => {
    expect(evidenceLane(coverage)?.segments).toEqual([
      { start: '2016-01-04', end: '2017-01-02', tone: 'neutral', label: 'No evidence' },
      { start: '2017-01-03', end: '2018-01-01', tone: 'warning', label: 'Partial evidence' },
      { start: '2018-01-02', end: '2018-06-01', tone: 'info', label: 'Full evidence' },
    ]);
  });

  it('is no lane without points', () => {
    expect(evidenceLane(history())).toBeNull();
    expect(evidenceLane(undefined)).toBeNull();
  });
});

describe('episodeBands', () => {
  const recessions: Recession[] = [
    { start: '2020-02-01', end: '2020-04-01', announcedStart: null, announcedEnd: null },
    { start: '2026-01-01', end: null, announcedStart: null, announcedEnd: null },
    { start: '2001-03-01', end: '2001-11-01', announcedStart: null, announcedEnd: null },
  ];

  it('shades a fall negative, a recovery positive and a recession neutral and hatched', () => {
    expect(episodeBands([episode()], recessions, window)).toEqual([
      {
        start: '2020-02-01',
        end: '2020-04-01',
        tone: 'neutral',
        label: BAND_LABELS.recession,
        pattern: 'hatch',
      },
      {
        start: '2026-01-01',
        end: '2026-10-02',
        tone: 'neutral',
        label: BAND_LABELS.recession,
        pattern: 'hatch',
      },
      { start: '2020-02-19', end: '2020-03-23', tone: 'negative', label: BAND_LABELS.fall },
      { start: '2020-03-23', end: '2020-08-18', tone: 'positive', label: BAND_LABELS.recovery },
    ]);
  });

  it('draws no recovery before the S&P 500 has regained its peak', () => {
    expect(episodeBands([episode({ recovered: null })], [], window).map((b) => b.label)).toEqual([
      BAND_LABELS.fall,
    ]);
  });

  it('leaves out what lies outside the window', () => {
    expect(
      episodeBands([episode()], recessions, { start: '2021-01-04', end: '2025-12-31' }),
    ).toEqual([]);
  });
});

describe('toHistoryChart', () => {
  it('assembles the lines, the lanes that exist, the bands and a dashed threshold line', () => {
    const chart = toHistoryChart({
      series: [
        {
          id: 'nfci',
          label: 'Financial conditions',
          history: history({ points: [{ session: '2020-01-02', value: 0.4 }] }),
        },
      ],
      lanes: [signalLane(history({ segments: [] })), null],
      threshold: { value: 0.5, label: 'on' },
      episodes: [episode()],
      recessions: [],
      window,
    });
    expect(chart.series).toEqual([
      { id: 'nfci', label: 'Financial conditions', points: [{ time: '2020-01-02', value: 0.4 }] },
    ]);
    expect(chart.lanes.map((lane) => lane.id)).toEqual(['signal']);
    expect(chart.bands).toHaveLength(2);
    expect(chart.referenceLines).toEqual([
      { value: 0.5, label: 'on', tone: 'warning', dash: true },
    ]);
  });

  it('draws no reference line without a threshold and no line for a missing history', () => {
    const chart = toHistoryChart({
      series: [{ id: 'x', label: 'X', history: undefined }],
      lanes: [],
      threshold: null,
      episodes: [],
      recessions: [],
      window,
    });
    expect(chart.referenceLines).toEqual([]);
    expect(chart.series[0]?.points).toEqual([]);
  });
});
