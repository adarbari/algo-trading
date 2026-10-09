import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EDGES_FIXTURE, toEdges } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { EdgeDetail } from './EdgeDetail';

const hooks = vi.hoisted(() => ({ useEdges: vi.fn() }));
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdges: hooks.useEdges,
}));
vi.mock('@/features/edge-evaluation', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RunEvaluation: ({ edgeId }: { edgeId: string }) => <Text>{`run ${edgeId}`}</Text> };
});
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

beforeEach(() => {
  hooks.useEdges.mockReturnValue(fakeQuery(toEdges(EDGES_FIXTURE)));
});

describe('EdgeDetail', () => {
  it('shows the frozen figures per variant through the odds line, never an exploratory row', async () => {
    const { container } = render(<EdgeDetail id="momentum_12_1" />);
    expect(screen.getByRole('heading', { name: 'Momentum 12-1' })).toBeInTheDocument();
    expect(screen.getByText('run momentum_12_1')).toBeInTheDocument();
    expect(screen.getByText('momentum_12_1 (screener)')).toBeInTheDocument();
    expect(screen.getByText('equal_weight (baseline)')).toBeInTheDocument();
    expect(screen.getByText('58.0%')).toBeInTheDocument();
    expect(screen.queryByText('99.0%')).not.toBeInTheDocument();
    expect(screen.queryByText('90.0%')).not.toBeInTheDocument();
    for (const id of ['hit_rate', 'base_rate', 'lift', 'independent_sessions', 'edge_status']) {
      expect(screen.getAllByText(`help ${id}`).length).toBeGreaterThan(0);
    }
    await expectNoA11yViolations(container);
  });

  it('labels an exploratory run as such and lists the canonical one', () => {
    render(<EdgeDetail id="momentum_12_1" />);
    expect(screen.getByText('EXPLORATORY')).toBeInTheDocument();
    expect(screen.getByText('Canonical')).toBeInTheDocument();
    expect(screen.getByText('help exploratory')).toBeInTheDocument();
  });

  it('says why an edge has no run, with the rejection reason', () => {
    render(<EdgeDetail id="sp500_index_changes" />);
    expect(screen.getByText('not run yet')).toBeInTheDocument();
    expect(screen.getByText('The effect vanished after 2005.')).toBeInTheDocument();
    expect(screen.queryByText('EXPLORATORY')).not.toBeInTheDocument();
  });

  it('asks to choose an edge, and says when the chosen one does not exist', () => {
    const { rerender } = render(<EdgeDetail id={null} />);
    expect(screen.getByText('Choose an edge')).toBeInTheDocument();
    rerender(<EdgeDetail id="nope" />);
    expect(screen.getByText('No edge nope')).toBeInTheDocument();
  });

  it('shows loading and error states', () => {
    hooks.useEdges.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<EdgeDetail id="momentum_12_1" />);
    expect(screen.getByText('Loading edge…')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<EdgeDetail id="momentum_12_1" />);
    expect(screen.getByText('The edge failed to load.')).toBeInTheDocument();
  });
});
