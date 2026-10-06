import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartProps } from '@algotrade/ui';

import {
  regimeFixture,
  type Regime,
  type RegimeEpisode,
  type SeriesHistory,
} from '@/entities/regime';
import { fakeQuery } from '@/shared/lib/testing';

import { RegimeCycles } from './RegimeCycles';

const hooks = vi.hoisted(() => ({
  useRegime: vi.fn(),
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
  useRegime: hooks.useRegime,
  useMarketHistory: hooks.useMarketHistory,
  useRegimeEpisodes: hooks.useRegimeEpisodes,
}));

const regime = regimeFixture();
const history = (name: string, extra: Partial<SeriesHistory>): SeriesHistory => ({
  name,
  bucketSessions: 10,
  points: [],
  segments: [],
  ...extra,
});
const HISTORIES = [
  history('market.regime@v2.macro_risk', {
    points: [
      { session: '2008-09-05', value: 40 },
      { session: '2008-10-03', value: 71 },
    ],
  }),
  history('market.regime@v2.market_stress', {
    points: [
      { session: '2008-09-05', value: null },
      { session: '2008-10-03', value: 88 },
    ],
  }),
  history('market.regime@v2.label', {
    bucketSessions: 1,
    segments: [
      { start: '2008-09-05', end: '2008-09-30', value: 'CAUTION' },
      { start: '2008-10-01', end: '2008-10-03', value: 'CRISIS' },
    ],
  }),
  history('market.regime@v2.market_coverage', {
    points: [
      { session: '2008-09-05', value: 0.4 },
      { session: '2008-10-03', value: 1 },
    ],
  }),
];

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regime));
  hooks.useMarketHistory.mockReturnValue(fakeQuery(HISTORIES));
  hooks.useRegimeEpisodes.mockReturnValue(
    fakeQuery({
      episodes: [
        {
          key: 'gfc',
          peak: '2007-10-09',
          trough: '2009-03-09',
          recovered: '2013-03-28',
        } as RegimeEpisode,
      ],
      recessions: [
        { start: '2007-12-01', end: '2009-06-01', announcedStart: null, announcedEnd: null },
      ],
    }),
  );
});

const lastProps = (): ChartProps => (hooks.chart.mock.calls.at(-1) as [ChartProps])[0];

describe('RegimeCycles', () => {
  it('asks for both scores, the label and the market coverage over every year stored', () => {
    render(<RegimeCycles />);
    expect(hooks.useMarketHistory).toHaveBeenCalledWith(
      [
        'market.regime@v2.macro_risk',
        'market.regime@v2.market_stress',
        'market.regime@v2.label',
        'market.regime@v2.market_coverage',
      ],
      '1971-01-01',
      '2026-10-02',
      600,
    );
    expect(screen.getByRole('region', { name: 'Scores through the cycles' })).toBeVisible();
    expect(screen.getByText('Macro risk and market stress scores, 0 to 100 (ready)')).toBeVisible();
    expect(screen.getByRole('radiogroup', { name: 'Chart range' })).toBeVisible();
  });

  it('draws both lines (a gap stays a gap), a line at 50, the regime and evidence lanes and the bands', () => {
    render(<RegimeCycles />);
    const props = lastProps();
    expect(props.series.map((s) => s.label)).toEqual(['Macro risk', 'Market stress']);
    expect(props.series[1]?.points[0]).toEqual({ time: '2008-09-05', value: null });
    expect(props.referenceLines).toEqual([
      { value: 50, label: 'high', tone: 'warning', dash: true },
    ]);
    expect(props.lanes?.map((lane) => lane.label)).toEqual(['Regime', 'Evidence']);
    expect(props.lanes?.[0]?.segments.map((s) => [s.tone, s.label])).toEqual([
      ['warning', 'Clouds building'],
      ['negative', 'Severe storm'],
    ]);
    expect(props.lanes?.[1]?.segments.map((s) => s.label)).toEqual([
      'Partial evidence',
      'Full evidence',
    ]);
    expect(props.bands?.map((b) => b.label)).toEqual([
      'NBER recession',
      'Market fall, peak to trough',
      'Recovery, trough to new high',
    ]);
  });

  it('shows the chart loading, and failing with its own message', () => {
    hooks.useMarketHistory.mockReturnValue(fakeQuery<SeriesHistory[]>(undefined));
    const { rerender } = render(<RegimeCycles />);
    expect(lastProps().status).toBe('loading');
    hooks.useMarketHistory.mockReturnValue(
      fakeQuery<SeriesHistory[]>(undefined, { isError: true }),
    );
    rerender(<RegimeCycles />);
    expect(lastProps().status).toBe('error');
    expect(lastProps().errorMessage).toBe('The score history failed to load.');
  });

  it('says there is nothing to chart when no scores are stored', () => {
    hooks.useMarketHistory.mockReturnValue(fakeQuery<SeriesHistory[]>([]));
    render(<RegimeCycles />);
    expect(lastProps().series.every((s) => s.points.length === 0)).toBe(true);
    expect(lastProps().emptyMessage).toBe('No scores are stored in this range.');
  });

  it('is empty when no regime is stored, loading before the answer and an error on failure', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    const { rerender } = render(<RegimeCycles />);
    expect(screen.getByText(/no score history to show/)).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<RegimeCycles />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the score history');
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined, { isError: true }));
    rerender(<RegimeCycles />);
    expect(screen.getByText('The score history failed to load.')).toBeVisible();
  });
});
