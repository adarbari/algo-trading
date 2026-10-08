import type { ChartProps } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { emptyUsage, usageFixture } from '@/entities/llm-usage';
import { gql, TestQueryProvider } from '@/shared/api';

import { UsageTrendPanel } from './UsageTrendPanel';

const charts = vi.hoisted(() => ({ chart: vi.fn() }));

vi.mock('@algotrade/ui', async (importOriginal) => {
  const ui = await importOriginal<Record<string, unknown>>();
  const { Text } = await import('@algotrade/ui');
  return {
    ...ui,
    // jsdom has no canvas: the chart is checked by the props it receives.
    Chart: (props: ChartProps) => {
      charts.chart(props);
      return <Text>{props.label}</Text>;
    },
  };
});
vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const view = (data: unknown) => {
  vi.mocked(gql).mockResolvedValue({ llmUsage: data });
  return render(
    <TestQueryProvider>
      <UsageTrendPanel />
    </TestQueryProvider>,
  );
};

describe('UsageTrendPanel', () => {
  beforeEach(() => {
    charts.chart.mockClear();
  });

  it('draws the daily cost and tokens, the notional cost as its own line', async () => {
    view(usageFixture());
    expect(await screen.findByText('Cost per day')).toBeInTheDocument();
    expect(screen.getByText('Tokens per day')).toBeInTheDocument();
    const cost = charts.chart.mock.calls
      .map((c) => c[0] as ChartProps)
      .find((p) => p.label === 'Cost per day');
    expect(cost?.series.map((s) => s.label)).toEqual([
      'Counts against the budget',
      'Notional (reported)',
    ]);
    expect(cost?.series[0]?.points).toHaveLength(3);
    expect(cost?.series[0]?.points[0]?.value).toBe(0);
    const tokens = charts.chart.mock.calls
      .map((c) => c[0] as ChartProps)
      .find((p) => p.label === 'Tokens per day');
    expect(tokens?.series[0]?.points.map((p) => p.value)).toEqual([null, 100, 200]);
  });

  it('says when nothing is recorded', async () => {
    view(emptyUsage());
    expect(await screen.findByText('No text-model calls recorded yet')).toBeInTheDocument();
  });
});
