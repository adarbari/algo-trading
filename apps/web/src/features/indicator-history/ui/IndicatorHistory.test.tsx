import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Text, type ChartProps } from '@algotrade/ui';

import {
  regimeFixture,
  type RegimeEpisode,
  type RegimeIndicator,
  type SeriesHistory,
} from '@/entities/regime';
import { fakeQuery } from '@/shared/lib/testing';

import { IndicatorHistory } from './IndicatorHistory';

const hooks = vi.hoisted(() => ({
  useMarketHistory: vi.fn(),
  useRegimeEpisodes: vi.fn(),
  chart: vi.fn(),
}));

vi.mock('@algotrade/ui', async (importOriginal) => {
  const ui = await importOriginal<Record<string, unknown>>();
  const { Text } = await import('@algotrade/ui');
  return {
    ...ui,
    // jsdom has no canvas: the chart is checked by the props it receives.
    Chart: (props: ChartProps) => {
      hooks.chart(props);
      return (
        <>
          <Text>{`${props.label} (${props.status ?? 'ready'})`}</Text>
          {props.toolbar}
        </>
      );
    },
  };
});
vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useMarketHistory: hooks.useMarketHistory,
  useRegimeEpisodes: hooks.useRegimeEpisodes,
}));

const [curve, nfci] = regimeFixture().indicators as [RegimeIndicator, RegimeIndicator];
const window = { start: '1971-01-01', end: '2026-10-02' };

const line: SeriesHistory = {
  name: nfci.feature,
  bucketSessions: 5,
  points: [
    { session: '2020-03-06', value: 0.1 },
    { session: '2020-03-13', value: null },
    { session: '2020-03-20', value: 0.7 },
  ],
  segments: [],
};
const verdict: SeriesHistory = {
  name: nfci.verdictFeature,
  bucketSessions: 1,
  points: [],
  segments: [
    { start: '2020-03-20', end: '2020-04-03', value: 'ON' },
    { start: '2020-04-10', end: '2020-05-01', value: 'OFF' },
  ],
};
const covid = {
  key: 'covid_2020',
  peak: '2020-02-19',
  trough: '2020-03-23',
  recovered: '2020-08-18',
} as RegimeEpisode;

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useMarketHistory.mockReset();
  hooks.useRegimeEpisodes.mockReturnValue(
    fakeQuery({
      episodes: [covid],
      recessions: [
        { start: '2020-02-01', end: '2020-04-01', announcedStart: null, announcedEnd: null },
      ],
    }),
  );
});

const lastProps = (): ChartProps => (hooks.chart.mock.calls.at(-1) as [ChartProps])[0];

describe('IndicatorHistory', () => {
  it('reads the value and its verdict over the window and draws the line, lane, bands and threshold', () => {
    hooks.useMarketHistory.mockReturnValue(fakeQuery([line, verdict]));
    render(<IndicatorHistory indicator={nfci} window={window} toolbar={null} />);
    expect(hooks.useMarketHistory).toHaveBeenCalledWith(
      [nfci.feature, nfci.verdictFeature],
      '1971-01-01',
      '2026-10-02',
      600,
    );
    const props = lastProps();
    expect(props.series[0]?.points).toEqual([
      { time: '2020-03-06', value: 0.1 },
      { time: '2020-03-13', value: null },
      { time: '2020-03-20', value: 0.7 },
    ]);
    expect(props.lanes?.[0]).toMatchObject({
      label: 'Signal',
      segments: [{ tone: 'warning', label: 'Signal on' }],
    });
    expect(props.bands?.map((b) => [b.tone, b.pattern ?? 'solid'])).toEqual([
      ['neutral', 'hatch'],
      ['negative', 'solid'],
      ['positive', 'solid'],
    ]);
    expect(props.referenceLines).toEqual([
      { value: 0.5, label: 'on', tone: 'warning', dash: true },
    ]);
    expect(screen.getByText(/Colors as in the legend above/)).toBeVisible();
  });

  it('draws no threshold line for a card with no rule, and renders the toolbar it is given', () => {
    hooks.useMarketHistory.mockReturnValue(fakeQuery([line, verdict]));
    render(
      <IndicatorHistory
        indicator={{ ...curve, threshold: null }}
        window={window}
        toolbar={<Text>range control</Text>}
      />,
    );
    expect(lastProps().referenceLines).toEqual([]);
    expect(screen.getByText('range control')).toBeVisible();
  });

  it('shows the chart loading, then failing with a retry', () => {
    hooks.useMarketHistory.mockReturnValue(fakeQuery<SeriesHistory[]>(undefined));
    const { rerender } = render(
      <IndicatorHistory indicator={nfci} window={window} toolbar={null} />,
    );
    expect(lastProps().status).toBe('loading');
    hooks.useMarketHistory.mockReturnValue(
      fakeQuery<SeriesHistory[]>(undefined, { isError: true }),
    );
    rerender(<IndicatorHistory indicator={nfci} window={window} toolbar={null} />);
    expect(lastProps().status).toBe('error');
  });

  it('gives the chart no points when nothing is stored, so it says so', () => {
    hooks.useMarketHistory.mockReturnValue(fakeQuery<SeriesHistory[]>([]));
    render(<IndicatorHistory indicator={nfci} window={window} toolbar={null} />);
    expect(lastProps().series[0]?.points).toEqual([]);
    expect(lastProps().emptyMessage).toBe('Nothing is stored for this indicator in this range.');
  });

  it('still draws the line when the episodes did not load', () => {
    hooks.useMarketHistory.mockReturnValue(fakeQuery([line, verdict]));
    hooks.useRegimeEpisodes.mockReturnValue(fakeQuery(undefined, { isError: true }));
    render(<IndicatorHistory indicator={nfci} window={window} toolbar={null} />);
    expect(lastProps().bands).toEqual([]);
    expect(lastProps().series[0]?.points).toHaveLength(3);
  });
});
