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

import { EdgeCosts } from './EdgeCosts';
import { EdgeDrawdown } from './EdgeDrawdown';
import { EdgeYears } from './EdgeYears';

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
describe('Setup record: drawdown', () => {
  it('opens the drawdown: the underwater curve, the deepest drops and the volatility', () => {
    render(<EdgeDrawdown edgeId="momentum_12_1" />);
    const props = hooks.chart.mock.calls.at(-1)?.[0] as ChartProps;
    expect(props.series[0]).toMatchObject({ id: 'underwater', type: 'underwater' });
    expect(props.series[0]?.points.at(-1)).toEqual({ time: '2026-06-03', value: -0.01 });
    const episodes = screen.getByRole('grid', { name: 'Deepest drawdowns' });
    expect(within(episodes).getByText('Not yet')).toBeInTheDocument();
    const strip = screen.getByRole('region', { name: 'Drawdown and volatility' });
    expect(strip).toHaveTextContent('12.0%');
    expect(strip).toHaveTextContent('—'); // out-of-sample volatility not stored: missing, not zero
  });

  it('says why an outcome with no return has no drawdown', () => {
    hooks.useEdgeDrawdown.mockReturnValue(
      fakeQuery({ ...DRAWDOWN_FIXTURE, points: [], episodes: [], unknown: UNKNOWN_FIXTURE }),
    );
    render(<EdgeDrawdown edgeId="momentum_12_1" />);
    expect(screen.getByText('not stored for this run')).toBeInTheDocument();
    expect(hooks.chart).not.toHaveBeenCalled();
  });

  it('says an outcome that is not a return is not a return, with its Guide term and no gap', () => {
    hooks.useEdgeDrawdown.mockReturnValue(
      fakeQuery({ ...DRAWDOWN_FIXTURE, state: 'not_a_return', points: [], episodes: [] }),
    );
    render(<EdgeDrawdown edgeId="momentum_12_1" />);
    expect(screen.getByText('Not a return')).toBeInTheDocument();
    expect(screen.getByText('help not_a_return')).toBeInTheDocument();
    expect(screen.queryByText(/NOT_A_RETURN|unit:/)).not.toBeInTheDocument();
    expect(hooks.chart).not.toHaveBeenCalled();
  });

  it('shows the drawdown loading and failed with a retry', async () => {
    hooks.useEdgeDrawdown.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<EdgeDrawdown edgeId="momentum_12_1" />);
    expect(screen.getByText('Loading the drawdown')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeDrawdown.mockReturnValue(failed);
    rerender(<EdgeDrawdown edgeId="momentum_12_1" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });

  it('splits the year of the split into in-sample and out-of-sample rows', async () => {
    const { container } = render(<EdgeYears years={verdict.years} />);
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
    await expectNoA11yViolations(container);
  });

  it('shows the cost strip with its break-even, and says an outcome that is not a return has none', async () => {
    const { rerender } = render(<EdgeCosts edgeId="momentum_12_1" />);
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
    rerender(<EdgeCosts edgeId="momentum_12_1" />);
    expect(screen.getByText('Not a cost outcome')).toBeInTheDocument();
    expect(screen.getByText('help cost_state')).toBeInTheDocument();
  });
});
