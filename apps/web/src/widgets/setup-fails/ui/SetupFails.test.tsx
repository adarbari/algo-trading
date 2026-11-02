import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartProps } from '@algotrade/ui';

import {
  COSTS_FIXTURE,
  DRAWDOWN_FIXTURE,
  HORIZONS_FIXTURE,
  REGIMES_FIXTURE,
} from '@/entities/edge';
import { fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeHorizons } from './EdgeHorizons';
import { EdgeRegimes } from './EdgeRegimes';

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

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useEdgeDrawdown.mockReturnValue(fakeQuery(DRAWDOWN_FIXTURE));
  hooks.useEdgeRegimes.mockReturnValue(fakeQuery(REGIMES_FIXTURE));
  hooks.useEdgeHorizons.mockReturnValue(fakeQuery(HORIZONS_FIXTURE));
  hooks.useEdgeCosts.mockReturnValue(fakeQuery(COSTS_FIXTURE));
});
describe('Setup fails: regimes and holding period', () => {
  it('opens the regime view: a figure per regime and period, no trades and a thin one said in words', async () => {
    render(<EdgeRegimes edgeId="momentum_12_1" />);
    const table = screen.getByRole('grid', { name: 'By regime' });
    expect(within(table).getByText('Calm')).toBeInTheDocument();
    expect(within(table).getAllByText('No trades').length).toBeGreaterThan(0);
    expect(within(table).getByText('n=1')).toBeInTheDocument(); // crisis rests on one trade
    await userEvent.click(periodRadio('In-sample'));
    expect(within(table).getAllByText('Not stored')).toHaveLength(3); // crisis has no in-sample side
    expect(screen.getByText('help by_regime')).toBeInTheDocument();
  });

  it('names the regime no scale covers Unclassified, with its Guide term', () => {
    hooks.useEdgeRegimes.mockReturnValue(
      fakeQuery({
        ...REGIMES_FIXTURE,
        rows: [{ ...REGIMES_FIXTURE.rows[0], regime: 'UNKNOWN' }],
      }),
    );
    render(<EdgeRegimes edgeId="momentum_12_1" />);
    const table = screen.getByRole('grid', { name: 'By regime' });
    expect(within(table).getByText('Unclassified')).toBeInTheDocument();
    expect(within(table).queryByText('UNKNOWN')).not.toBeInTheDocument();
    expect(within(table).getByText('help regime')).toBeInTheDocument();
  });

  it('opens the holding-period view: the basis marked, the others not the pre-chosen test, and the count date', () => {
    render(<EdgeHorizons edgeId="momentum_12_1" />);
    const table = screen.getByRole('grid', { name: 'By holding period' });
    expect(within(table).getByText('Verdict basis')).toBeInTheDocument();
    expect(within(table).getAllByText('not the pre-chosen test')).toHaveLength(1); // not the basis row
    expect(within(table).getByText('40 OOS by')).toBeInTheDocument();
    expect(within(table).getByText('Beyond the projection')).toBeInTheDocument(); // no date for the basis
  });

  it('shows the regime read failed with a retry', async () => {
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeRegimes.mockReturnValue(failed);
    render(<EdgeRegimes edgeId="momentum_12_1" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
