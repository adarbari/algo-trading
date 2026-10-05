import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartProps } from '@algotrade/ui';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ComparePanel } from './ComparePanel';

const hooks = vi.hoisted(() => ({
  useComparePrices: vi.fn(),
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
}));

stubElementSize();

const closes = (a: number, b: number) => [
  { session: '2025-10-02', close: a },
  { session: '2025-10-03', close: b },
];

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useComparePrices.mockReturnValue(
    fakeQuery([
      { symbol: 'AAPL', instrumentId: 'EQ:A', closes: closes(200, 250) },
      { symbol: 'MSFT', instrumentId: 'EQ:M', closes: closes(500, 450) },
    ]),
  );
});

describe('ComparePanel', () => {
  it('charts the compare set rebased to 100, in the compare bar colours', async () => {
    const { container } = render(
      <ComparePanel symbols={['AAPL', 'MSFT']} range="1Y" onRangeChange={vi.fn()} />,
    );
    const chart = hooks.chart.mock.lastCall?.[0] as ChartProps;
    expect(chart.label).toBe('AAPL, MSFT rebased to 100');
    expect(chart.series.map((s) => [s.id, s.tone, s.points.map((p) => p.value)])).toEqual([
      ['AAPL', 's1', [100, 125]],
      ['MSFT', 's2', [100, 90]],
    ]);
    expect(screen.getByRole('radio', { name: '1Y' })).toBeChecked();
    await expectNoA11yViolations(container);
  });

  it('asks for tickers when the compare set is empty', () => {
    render(<ComparePanel symbols={[]} range="1Y" onRangeChange={vi.fn()} />);
    expect(screen.getByText('Nothing to compare yet')).toBeInTheDocument();
  });
});
