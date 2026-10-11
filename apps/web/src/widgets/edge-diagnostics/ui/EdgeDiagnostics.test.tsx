import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartProps } from '@algotrade/ui';

import {
  CAPACITY_FIXTURE,
  MONTHLY_FIXTURE,
  ROLLING_STARTS_FIXTURE,
  UNKNOWN_FIXTURE,
  VARIANTS_FIXTURE,
} from '@/entities/edge';
import { fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeDiagnostics } from './EdgeDiagnostics';

const hooks = vi.hoisted(() => ({
  useEdgeVariants: vi.fn(),
  useEdgeRollingStarts: vi.fn(),
  useEdgeCapacity: vi.fn(),
  useEdgeMonthly: vi.fn(),
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
  useEdgeVariants: hooks.useEdgeVariants,
  useEdgeRollingStarts: hooks.useEdgeRollingStarts,
  useEdgeCapacity: hooks.useEdgeCapacity,
  useEdgeMonthly: hooks.useEdgeMonthly,
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

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useEdgeVariants.mockReturnValue(fakeQuery(VARIANTS_FIXTURE));
  hooks.useEdgeRollingStarts.mockReturnValue(fakeQuery(ROLLING_STARTS_FIXTURE));
  hooks.useEdgeCapacity.mockReturnValue(fakeQuery(CAPACITY_FIXTURE));
  hooks.useEdgeMonthly.mockReturnValue(fakeQuery(MONTHLY_FIXTURE));
});

describe('EdgeDiagnostics', () => {
  it('shows the variant grid, the rolling starts, the capacity and the monthly map', async () => {
    render(<EdgeDiagnostics edgeId="momentum_12_1" />);
    const grid = screen.getByRole('grid', {
      name: 'Variant grid: lift in points by holding period',
    });
    expect(within(grid).getByText('Verdict basis')).toBeInTheDocument();
    expect(within(grid).getAllByText('not the pre-chosen test')).toHaveLength(1);
    expect(screen.getByText('6 variants tried')).toBeInTheDocument();
    const props = hooks.chart.mock.calls.at(-1)?.[0] as ChartProps;
    expect(props.series[0]?.points).toEqual([
      { time: '2025-01-02', value: 2.1 },
      { time: '2025-07-01', value: -0.5 },
    ]);
    expect(screen.getByText('Picks under the floor')).toBeInTheDocument();
    expect(screen.getByText('Universe floor, 20-day dollar volume')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    expect(screen.getByText('Hidden')).toBeInTheDocument(); // the all-period capacity is withheld
    const map = screen.getByRole('grid', { name: 'Gain or loss of the curve by month' });
    expect(within(map).getByText('2026 · Out-of-sample')).toBeInTheDocument(); // the split's side
    expect(within(map).getByText('+1.0%')).toBeInTheDocument();
    for (const id of ['variant_grid', 'rolling_starts', 'capacity', 'monthly_map']) {
      expect(screen.getByText(`help ${id}`)).toBeInTheDocument();
    }
  });

  it('sizes a position against the median pick and shows the floor row only when it binds', () => {
    const { unmount } = render(<EdgeDiagnostics edgeId="momentum_12_1" />);
    expect(screen.getByText(/position, share of the median pick's volume/)).toBeInTheDocument();
    unmount();
    hooks.useEdgeCapacity.mockReturnValue(
      fakeQuery({ ...CAPACITY_FIXTURE, floorBinds: false, universeFloorUsd: 50_000_000 }),
    );
    render(<EdgeDiagnostics edgeId="momentum_12_1" />);
    expect(screen.queryByText('Picks under the floor')).not.toBeInTheDocument();
    expect(screen.queryByText('Universe floor, 20-day dollar volume')).not.toBeInTheDocument();
    expect(screen.getByText(/position, share of the median pick's volume/)).toBeInTheDocument();
  });

  it('says why a section has no figures, and shows its read failed with a retry', async () => {
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeVariants.mockReturnValue(
      fakeQuery({ ...VARIANTS_FIXTURE, unknown: UNKNOWN_FIXTURE }),
    );
    hooks.useEdgeMonthly.mockReturnValue(failed);
    hooks.useEdgeRollingStarts.mockReturnValue(
      fakeQuery({ ...ROLLING_STARTS_FIXTURE, starts: [], unknown: UNKNOWN_FIXTURE }),
    );
    render(<EdgeDiagnostics edgeId="momentum_12_1" />);
    expect(screen.getAllByText('not stored for this run').length).toBe(2);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
