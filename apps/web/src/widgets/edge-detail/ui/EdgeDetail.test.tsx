import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EDGES_FIXTURE } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeDetail } from './EdgeDetail';

const hooks = vi.hoisted(() => ({
  useEdges: vi.fn(),
  useEdgeCompare: vi.fn(),
  useEdgePaper: vi.fn(),
}));
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdges: hooks.useEdges,
  useEdgePaper: hooks.useEdgePaper,
}));
vi.mock('@/features/edge-evaluation', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RunEvaluation: ({ edgeId }: { edgeId: string }) => <Text>{`run ${edgeId}`}</Text> };
});
vi.mock('@/features/edge-follow', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    EdgeActions: ({ edge }: { edge: { id: string } }) => <Text>{`actions ${edge.id}`}</Text>,
  };
});
vi.mock('@/features/edge-compare', () => ({ useEdgeCompare: hooks.useEdgeCompare }));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

stubElementSize();

beforeEach(() => {
  hooks.useEdges.mockReturnValue(fakeQuery(EDGES_FIXTURE.edges));
  hooks.useEdgePaper.mockReturnValue(fakeQuery(null));
  hooks.useEdgeCompare.mockReturnValue(
    fakeQuery({
      oosHidden: true,
      reason: '',
      rows: [
        {
          label: 'My momentum',
          basis: 'momentum_12_1, 20 trading days',
          inSample: { winRate: 0.6, baseRate: 0.5, liftPts: 10, trades: 40 },
          outOfSample: null,
        },
        {
          label: 'Momentum 12-1',
          basis: 'momentum_12_1, 20 trading days',
          inSample: { winRate: 0.58, baseRate: 0.5, liftPts: 8, trades: 70 },
          outOfSample: { winRate: 0.57, baseRate: 0.52, liftPts: 5, trades: 6 },
        },
      ],
    }),
  );
});

describe('EdgeDetail', () => {
  it('shows the verdict, the server headline, the figures and the actions', async () => {
    const { container } = render(
      <EdgeDetail id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Momentum 12-1' })).toBeInTheDocument();
    expect(screen.getAllByText('Promising').length).toBeGreaterThan(0);
    expect(screen.getByText(/Out-of-sample, momentum_12_1, 20 trading days/)).toBeInTheDocument();
    expect(screen.getByText('run momentum_12_1')).toBeInTheDocument();
    expect(screen.getByText('actions momentum_12_1')).toBeInTheDocument();
    expect(screen.getByText(/^Site edge · /)).toBeInTheDocument();
    expect(screen.queryByRole('grid', { name: 'Compare versions' })).not.toBeInTheDocument();
    expect(hooks.useEdgeCompare).not.toHaveBeenCalled(); // a site edge has no comparison
    const strip = screen.getByRole('region', { name: 'Out-of-sample result' });
    expect(within(strip).getByText('57%')).toBeInTheDocument();
    expect(within(strip).getByText('+5 pts')).toBeInTheDocument();
    for (const id of [
      'win_rate',
      'base_rate',
      'lift',
      'trades',
      'verdict',
      'edge_status',
      'edge_state',
      'edge_copy',
    ]) {
      expect(screen.getAllByText(`help ${id}`).length).toBeGreaterThan(0);
    }
    await expectNoA11yViolations(container);
  });

  it('shows whose edge it is and the date of the official result in the header', () => {
    render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText('Site edge · Candidate')).toBeInTheDocument();
    expect(screen.getByText('Last backtest 5 Oct (official result)')).toBeInTheDocument();
    expect(screen.getAllByText('help official_result').length).toBeGreaterThan(0);
  });

  it('draws the in-sample decile bars and places the lift among the random-pick backtests', async () => {
    render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    const bars = await screen.findByRole('list', { name: 'Mean outcome by decile' });
    const rows = within(bars).getAllByRole('listitem');
    expect(rows).toHaveLength(10);
    expect(rows[0]).toHaveTextContent('Decile 1+9.0%');
    expect(rows[9]).toHaveTextContent('Decile 10−7.0%');
    expect(
      screen.getByText('Beats 96% of 1,000 random backtests after 3 variants tried.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Lift of random-pick backtests/ })).toBeInTheDocument();
    expect(screen.getByText('help robustness')).toBeInTheDocument();
  });

  it('says what is missing instead of drawing zeros when a run stored no deciles or draws', async () => {
    render(<EdgeDetail id="sp500_index_changes" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(await screen.findByText('Not stored for this result.')).toBeInTheDocument();
    expect(screen.getByText('No random-pick backtests for this result.')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Mean outcome by decile' })).not.toBeInTheDocument();
  });

  it('defines the edge in six parts, with screens linked and sources linked only with a url', () => {
    render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    for (const label of ['1 · Idea', '2 · Screens', '3 · Picks', '4 · Trade', '6 · Test']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'momentum_12_1' })).toHaveAttribute(
      'href',
      '/screeners/momentum_12_1',
    );
    expect(screen.getByRole('link', { name: /Jegadeesh and Titman 1993/ })).toHaveAttribute(
      'href',
      'https://example.org/jt1993',
    );
    expect(screen.getByText('Daniel and Moskowitz 2016')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Daniel/ })).not.toBeInTheDocument();
  });

  it('switches the year table between in-sample, out-of-sample and both', async () => {
    render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    const years = () => screen.getByRole('grid', { name: 'Year by year' });
    expect(within(years()).getByText('2026')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'In-sample' }));
    expect(within(years()).getByText('2025')).toBeInTheDocument();
    expect(within(years()).queryByText('2026')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Out-of-sample' }));
    expect(within(years()).getByText('No years to show')).toBeInTheDocument();
  });

  it('keeps the tests and backtests in the details', async () => {
    render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByText('Details'));
    expect(screen.getByText('Official result')).toBeInTheDocument();
    expect(screen.getByText('EXPLORATORY')).toBeInTheDocument();
    expect(screen.getByText('momentum_12_1: rollup (4 sessions)')).toBeInTheDocument();
    expect(screen.getByText('Not measured yet')).toBeInTheDocument();
  });

  it("shows a copy's origin, its labels and the comparison with the out-of-sample hidden", async () => {
    hooks.useEdges.mockReturnValue(
      fakeQuery(
        EDGES_FIXTURE.edges.map((e) =>
          e.id === 'my_momentum' ? { ...e, labels: ['followed_against_verdict'] } : e,
        ),
      ),
    );
    render(<EdgeDetail id="my_momentum" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText(/^Your edge · extends momentum_12_1/)).toBeInTheDocument();
    expect(screen.getByText('Followed against the verdict')).toBeInTheDocument();
    const table = await screen.findByRole('grid', { name: 'Compare versions' });
    expect(within(table).getByText('Momentum 12-1')).toBeInTheDocument();
    expect(within(table).getByText('In-sample win rate')).toBeInTheDocument();
    expect(within(table).queryByText('Out-of-sample win rate')).not.toBeInTheDocument();
  });

  it('says what a waiting edge waits on and offers the way back', async () => {
    const onBack = vi.fn();
    render(<EdgeDetail id="sp500_index_changes" onBack={onBack} onEdit={vi.fn()} />);
    expect(screen.getAllByText('No official result yet').length).toBeGreaterThan(0);
    expect(screen.getByText('The effect vanished after 2005.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '← Edges' }));
    expect(onBack).toHaveBeenCalled();
  });

  it('says when the chosen edge does not exist, and shows loading and error', () => {
    const { rerender } = render(<EdgeDetail id="nope" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText('No edge nope')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined));
    rerender(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText('Loading edge…')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText('The edge failed to load.')).toBeInTheDocument();
  });
});
