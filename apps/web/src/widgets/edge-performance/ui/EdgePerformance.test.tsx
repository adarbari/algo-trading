import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartProps } from '@algotrade/ui';

import {
  COSTS_FIXTURE,
  DRAWDOWN_FIXTURE,
  edgeFixture,
  HORIZONS_FIXTURE,
  REGIMES_FIXTURE,
  UNKNOWN_FIXTURE,
} from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgePerformance } from './EdgePerformance';

const hooks = vi.hoisted(() => ({
  useEdgeDrawdown: vi.fn(),
  useEdgeRegimes: vi.fn(),
  useEdgeHorizons: vi.fn(),
  useEdgeCosts: vi.fn(),
  chart: vi.fn(),
}));

vi.mock('@algotrade/ui', async (importOriginal) => {
  const ui = await importOriginal<Record<string, unknown>>();
  const { Text } = await import('@algotrade/ui');
  return {
    ...ui,
    Chart: (props: ChartProps) => {
      hooks.chart(props);
      return <Text>{props.label}</Text>;
    },
  };
});
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdgeDrawdown: hooks.useEdgeDrawdown,
  useEdgeRegimes: hooks.useEdgeRegimes,
  useEdgeHorizons: hooks.useEdgeHorizons,
  useEdgeCosts: hooks.useEdgeCosts,
}));
vi.mock('@/entities/availability', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    UnknownNote: ({ unknown }: { unknown: { kindText: string } }) => (
      <Text>{unknown.kindText}</Text>
    ),
  };
});
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

stubElementSize();

const periodRadio = (name: string) =>
  within(screen.getByRole('radiogroup', { name: 'Period shown' })).getByRole('radio', { name });

const verdict = edgeFixture('momentum_12_1').verdict;

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useEdgeDrawdown.mockReturnValue(fakeQuery(DRAWDOWN_FIXTURE));
  hooks.useEdgeRegimes.mockReturnValue(fakeQuery(REGIMES_FIXTURE));
  hooks.useEdgeHorizons.mockReturnValue(fakeQuery(HORIZONS_FIXTURE));
  hooks.useEdgeCosts.mockReturnValue(fakeQuery(COSTS_FIXTURE));
});

describe('EdgePerformance', () => {
  it('splits the year of the split into in-sample and out-of-sample rows', async () => {
    const { container } = render(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Where it worked' })).toBeInTheDocument();
    expect(screen.getByText('help edge_where_worked')).toBeInTheDocument();
    const years = () => screen.getByRole('grid', { name: 'Year by year' });
    const shown = (label: string) => within(years()).queryByText(label);
    expect(shown('2025')).toBeInTheDocument();
    expect(shown('2026 Jan–Mar')).toBeInTheDocument();
    expect(shown('2026 Apr–Dec')).toBeInTheDocument();
    await userEvent.click(periodRadio('In-sample'));
    expect(shown('2026 Apr–Dec')).not.toBeInTheDocument();
    await userEvent.click(periodRadio('Out-of-sample'));
    expect(shown('2026 Apr–Dec')).toBeInTheDocument();
    expect(shown('2025')).not.toBeInTheDocument();
    await userEvent.click(periodRadio('All'));
    expect(within(years()).getAllByText(/^2026 /)).toHaveLength(2);
    expect(hooks.useEdgeDrawdown).not.toHaveBeenCalled(); // the drawdown is read when its view opens
    await expectNoA11yViolations(container);
  });

  it('opens the drawdown: the underwater curve, the deepest drops and the volatility', async () => {
    render(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Drawdown' }));
    const props = hooks.chart.mock.calls.at(-1)?.[0] as ChartProps;
    expect(props.series[0]).toMatchObject({ id: 'underwater', type: 'underwater' });
    expect(props.series[0]?.points.at(-1)).toEqual({ time: '2026-06-03', value: -0.01 });
    const episodes = screen.getByRole('grid', { name: 'Deepest drawdowns' });
    expect(within(episodes).getByText('Not yet')).toBeInTheDocument();
    const strip = screen.getByRole('region', { name: 'Drawdown and volatility' });
    expect(strip).toHaveTextContent('12.0%');
    expect(strip).toHaveTextContent('—'); // out-of-sample volatility not stored: missing, not zero
  });

  it('says why an outcome with no return has no drawdown', async () => {
    hooks.useEdgeDrawdown.mockReturnValue(
      fakeQuery({ ...DRAWDOWN_FIXTURE, points: [], episodes: [], unknown: UNKNOWN_FIXTURE }),
    );
    render(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Drawdown' }));
    expect(screen.getByText('not stored for this run')).toBeInTheDocument();
    expect(hooks.chart).not.toHaveBeenCalled();
  });

  it('shows the drawdown loading and failed with a retry', async () => {
    hooks.useEdgeDrawdown.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Drawdown' }));
    expect(screen.getByText('Loading the drawdown')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeDrawdown.mockReturnValue(failed);
    rerender(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });

  it('opens the regime view: a figure per regime and period, no trades and a thin one said in words', async () => {
    render(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    expect(hooks.useEdgeRegimes).not.toHaveBeenCalled(); // read when its view opens
    await userEvent.click(screen.getByRole('tab', { name: 'Regime' }));
    const table = screen.getByRole('grid', { name: 'By regime' });
    expect(within(table).getByText('Calm')).toBeInTheDocument();
    expect(within(table).getAllByText('No trades').length).toBeGreaterThan(0);
    expect(within(table).getByText('n=1')).toBeInTheDocument(); // crisis rests on one trade
    await userEvent.click(periodRadio('In-sample'));
    expect(within(table).getAllByText('Not stored')).toHaveLength(3); // crisis has no in-sample side
    expect(screen.getByText('help by_regime')).toBeInTheDocument();
  });

  it('opens the holding-period view: the basis marked, the others not the pre-chosen test, and the count date', async () => {
    render(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Holding period' }));
    const table = screen.getByRole('grid', { name: 'By holding period' });
    expect(within(table).getByText('Verdict basis')).toBeInTheDocument();
    expect(within(table).getAllByText('not the pre-chosen test')).toHaveLength(1); // not the basis row
    expect(within(table).getByText('40 OOS by')).toBeInTheDocument();
    expect(within(table).getByText('Beyond the projection')).toBeInTheDocument(); // no date for the basis
  });

  it('shows the cost strip with its break-even, and says an outcome that is not a return has none', async () => {
    const { rerender } = render(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    const strip = screen.getByRole('region', { name: 'Lift at each round-trip cost' });
    expect(strip).toHaveTextContent("15 bp · the edge's cost");
    expect(strip).toHaveTextContent('Break-even, bp');
    expect(strip).toHaveTextContent('13');
    await userEvent.click(
      within(screen.getByRole('radiogroup', { name: 'Period of the costs' })).getByRole('radio', {
        name: 'All',
      }),
    );
    expect(screen.getByText('Not stored')).toBeInTheDocument(); // that period's cost rows
    hooks.useEdgeCosts.mockReturnValue(
      fakeQuery({ ...COSTS_FIXTURE, state: 'not_a_cost_outcome' }),
    );
    rerender(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    expect(screen.getByText('Not a cost outcome')).toBeInTheDocument();
    expect(screen.getByText('help cost_state')).toBeInTheDocument();
  });

  it('shows the regime and cost reads failed with a retry', async () => {
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeRegimes.mockReturnValue(failed);
    hooks.useEdgeCosts.mockReturnValue(fakeQuery(undefined));
    render(<EdgePerformance edgeId="momentum_12_1" verdict={verdict} />);
    expect(screen.getByText('Loading the costs')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Regime' }));
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
