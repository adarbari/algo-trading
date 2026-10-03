import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartProps } from '@algotrade/ui';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ComparePanel } from './ComparePanel';

const hooks = vi.hoisted(() => ({
  useComparePrices: vi.fn(),
  useCompareFeatures: vi.fn(),
  useFeatureCatalogue: vi.fn(),
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
          <Text>{props.label}</Text>
          {props.toolbar}
        </>
      );
    },
  };
});
vi.mock('@/entities/explore', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useComparePrices: hooks.useComparePrices,
  useCompareFeatures: hooks.useCompareFeatures,
}));
vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: hooks.useFeatureCatalogue,
}));

const CLOSE = 'rollup.price_stats@v2.close';
const CAP = 'feature.market_cap';
const instruments = [
  { instrument_id: 'EQ:A', symbol: 'AAPL' },
  { instrument_id: 'EQ:M', symbol: 'MSFT' },
];

stubElementSize();

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useComparePrices.mockReturnValue(
    fakeQuery({
      instruments,
      adjustment: 'splits',
      rebase: 100,
      start: '2025-10-02',
      end: '2025-10-03',
      dates: ['2025-10-02', '2025-10-03'],
      series: { 'EQ:A': [100, 101], 'EQ:M': [100, 99] },
    }),
  );
  hooks.useCompareFeatures.mockReturnValue(
    fakeQuery({
      session: '2026-10-02',
      instruments,
      missing: [],
      rows: [
        { feature: CLOSE, dtype: 'float32', values: { 'EQ:A': 333.69, 'EQ:M': 517.53 } },
        { feature: CAP, dtype: 'float', values: { 'EQ:A': 4.87e12, 'EQ:M': null } },
      ],
    }),
  );
  hooks.useFeatureCatalogue.mockReturnValue(
    fakeQuery([
      {
        name: CLOSE,
        unit: 'usd_per_share',
        dtype: 'float32',
        kind: 'window',
        scope: 'site',
        description: 'Close',
      },
      {
        name: CAP,
        unit: 'usd',
        dtype: 'float',
        kind: 'expression',
        scope: 'site',
        description: 'Cap',
      },
    ]),
  );
});

describe('ComparePanel', () => {
  it('charts the compare set rebased, in the compare bar colours, and lists dimensions', async () => {
    const { container } = render(
      <ComparePanel
        symbols={['AAPL', 'MSFT']}
        range="1Y"
        onRangeChange={vi.fn()}
        dimensions={[CLOSE, CAP]}
        onDimensionsChange={vi.fn()}
      />,
    );
    const chart = hooks.chart.mock.lastCall?.[0] as ChartProps;
    expect(chart.label).toBe('AAPL, MSFT rebased to 100');
    expect(chart.series.map((s) => [s.id, s.tone, s.points.length])).toEqual([
      ['AAPL', 's1', 2],
      ['MSFT', 's2', 2],
    ]);
    expect(screen.getByRole('radio', { name: '1Y' })).toBeChecked();
    const side = screen.getByRole('grid', { name: 'Side by side' });
    expect(within(side).getByText('Last close')).toBeInTheDocument();
    expect(within(side).getByText('$333.69')).toBeInTheDocument();
    expect(within(side).getByText('$4.87T')).toBeInTheDocument();
    expect(within(side).getByText('—')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dimension' })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('asks for tickers when the compare set is empty', () => {
    render(
      <ComparePanel
        symbols={[]}
        range="1Y"
        onRangeChange={vi.fn()}
        dimensions={[]}
        onDimensionsChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Nothing to compare yet')).toBeInTheDocument();
  });
});
