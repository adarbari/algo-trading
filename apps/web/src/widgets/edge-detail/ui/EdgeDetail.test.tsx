import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EDGES_FIXTURE } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeDetail } from './EdgeDetail';

const hooks = vi.hoisted(() => ({ useEdges: vi.fn(), useEdgePaper: vi.fn() }));
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdges: hooks.useEdges,
  useEdgePaper: hooks.useEdgePaper,
}));
vi.mock('@/features/edge-evaluation', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RunEvaluation: ({ edgeId }: { edgeId: string }) => <Text>{`run ${edgeId}`}</Text> };
});
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

stubElementSize();

beforeEach(() => {
  hooks.useEdges.mockReturnValue(fakeQuery(EDGES_FIXTURE.edges));
  hooks.useEdgePaper.mockReturnValue(fakeQuery(null));
});

describe('EdgeDetail', () => {
  it('shows the verdict, the server headline, the figures and the actions', async () => {
    const { container } = render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Momentum 12-1' })).toBeInTheDocument();
    expect(screen.getAllByText('Promising').length).toBeGreaterThan(0);
    expect(screen.getByText(/Out-of-sample, momentum_12_1, 20 trading days/)).toBeInTheDocument();
    expect(screen.getByText('run momentum_12_1')).toBeInTheDocument();
    const strip = screen.getByRole('region', { name: 'Out-of-sample result' });
    expect(within(strip).getByText('57%')).toBeInTheDocument();
    expect(within(strip).getByText('+5 pts')).toBeInTheDocument();
    for (const id of ['win_rate', 'base_rate', 'lift', 'trades', 'verdict', 'edge_status']) {
      expect(screen.getAllByText(`help ${id}`).length).toBeGreaterThan(0);
    }
    await expectNoA11yViolations(container);
  });

  it('defines the edge in six parts, with screens linked and sources linked only with a url', () => {
    render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} />);
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
    render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} />);
    const years = () => screen.getByRole('grid', { name: 'Year by year' });
    expect(within(years()).getByText('2026')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'In-sample' }));
    expect(within(years()).getByText('2025')).toBeInTheDocument();
    expect(within(years()).queryByText('2026')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Out-of-sample' }));
    expect(within(years()).getByText('No years to show')).toBeInTheDocument();
  });

  it('keeps the tests and backtests in the details', async () => {
    render(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} />);
    await userEvent.click(screen.getByText('Details'));
    expect(screen.getByText('Official result')).toBeInTheDocument();
    expect(screen.getByText('EXPLORATORY')).toBeInTheDocument();
    expect(screen.getByText('momentum_12_1: rollup (4 sessions)')).toBeInTheDocument();
    expect(screen.getByText('Not measured yet')).toBeInTheDocument();
  });

  it('says what a waiting edge waits on and offers the way back', async () => {
    const onBack = vi.fn();
    render(<EdgeDetail id="sp500_index_changes" onBack={onBack} />);
    expect(screen.getAllByText('No official result yet').length).toBeGreaterThan(0);
    expect(screen.getByText('The effect vanished after 2005.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '← Edges' }));
    expect(onBack).toHaveBeenCalled();
  });

  it('says when the chosen edge does not exist, and shows loading and error', () => {
    const { rerender } = render(<EdgeDetail id="nope" onBack={vi.fn()} />);
    expect(screen.getByText('No edge nope')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined));
    rerender(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} />);
    expect(screen.getByText('Loading edge…')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<EdgeDetail id="momentum_12_1" onBack={vi.fn()} />);
    expect(screen.getByText('The edge failed to load.')).toBeInTheDocument();
  });
});
