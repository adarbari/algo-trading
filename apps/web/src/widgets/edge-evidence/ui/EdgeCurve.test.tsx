import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartProps } from '@algotrade/ui';

import { CURVE_FIXTURE, UNKNOWN_FIXTURE } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { EdgeCurve } from './EdgeCurve';

const hooks = vi.hoisted(() => ({ useEdgeCurve: vi.fn(), chart: vi.fn() }));

vi.mock('@algotrade/ui', async (importOriginal) => {
  const ui = await importOriginal<Record<string, unknown>>();
  const { Text } = await import('@algotrade/ui');
  return {
    ...ui,
    // jsdom has no canvas: the chart is checked by the props it receives.
    Chart: (props: ChartProps) => {
      hooks.chart(props);
      return <Text>{props.label}</Text>;
    },
  };
});
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdgeCurve: hooks.useEdgeCurve,
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

beforeEach(() => {
  hooks.chart.mockClear();
  hooks.useEdgeCurve.mockReturnValue(fakeQuery(CURVE_FIXTURE));
});

describe('EdgeCurve', () => {
  it('draws the curve with its series, the split and the gaps, and explains it', async () => {
    const { container } = render(<EdgeCurve edgeId="momentum_12_1" />);
    expect(screen.getByRole('heading', { level: 3, name: 'Evidence curve' })).toBeInTheDocument();
    expect(screen.getByText('help evidence_curve')).toBeInTheDocument();
    expect(screen.getByText('Excess return, cumulative')).toBeInTheDocument();
    const props = hooks.chart.mock.calls.at(-1)?.[0] as ChartProps;
    expect(props.series.map((s) => s.id)).toEqual(['picks', 'base', 'live']);
    expect(props.bands?.map((b) => b.label)).toEqual(['In-sample', 'Out-of-sample']);
    expect(props.lanes?.[0]?.segments[0]?.label).toBe('Lost input');
    await expectNoA11yViolations(container);
  });

  it('says what the curve counts for an outcome with no return', () => {
    hooks.useEdgeCurve.mockReturnValue(fakeQuery({ ...CURVE_FIXTURE, kind: 'excess_wins' }));
    render(<EdgeCurve edgeId="momentum_12_1" />);
    expect(screen.getByText('Excess wins, cumulative')).toBeInTheDocument();
  });

  it('says a copy hides its out-of-sample result', () => {
    hooks.useEdgeCurve.mockReturnValue(fakeQuery({ ...CURVE_FIXTURE, hidden: true }));
    render(<EdgeCurve edgeId="my_momentum" />);
    expect(screen.getByText('Out-of-sample hidden')).toBeInTheDocument();
    expect(screen.getByText('help show_out_of_sample')).toBeInTheDocument();
  });

  it('gives the server reason, not an empty chart, when there is no curve', () => {
    hooks.useEdgeCurve.mockReturnValue(
      fakeQuery({ ...CURVE_FIXTURE, points: [], gaps: [], live: null, unknown: UNKNOWN_FIXTURE }),
    );
    render(<EdgeCurve edgeId="momentum_12_1" />);
    expect(screen.getByText('not stored for this run')).toBeInTheDocument();
    expect(hooks.chart).not.toHaveBeenCalled();
  });

  it('shows loading, then an error with a retry', async () => {
    hooks.useEdgeCurve.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<EdgeCurve edgeId="momentum_12_1" />);
    expect(screen.getByText('Loading the curve…')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeCurve.mockReturnValue(failed);
    rerender(<EdgeCurve edgeId="momentum_12_1" />);
    expect(screen.getByText('The curve failed to load.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
