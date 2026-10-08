import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EDGES_FIXTURE, toEdges } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeList } from './EdgeList';

const hooks = vi.hoisted(() => ({ useEdges: vi.fn() }));
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdges: hooks.useEdges,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

stubElementSize();

beforeEach(() => {
  hooks.useEdges.mockReturnValue(fakeQuery(toEdges(EDGES_FIXTURE)));
});

describe('EdgeList', () => {
  it('lists each edge with its status, frozen period and canonical run', async () => {
    const { container } = render(<EdgeList selected={null} onSelect={vi.fn()} />);
    const table = screen.getByRole('grid', { name: 'Edges' });
    const momentum = within(table).getByRole('row', { name: /Momentum 12-1/ });
    expect(within(momentum).getByText('Candidate')).toBeInTheDocument();
    expect(within(momentum).getByText('2024-01-01')).toBeInTheDocument();
    expect(within(momentum).getByText('run-frozen')).toBeInTheDocument();
    const rejected = within(table).getByRole('row', { name: /S&P 500 index changes/ });
    expect(within(rejected).getByText('Rejected')).toBeInTheDocument();
    expect(within(rejected).getByText('none')).toBeInTheDocument();
    expect(screen.getByText('help edge_status')).toBeInTheDocument();
    expect(screen.getByText('help frozen_period')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('selects an edge on a row click', async () => {
    const onSelect = vi.fn();
    render(<EdgeList selected={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('row', { name: /Momentum 12-1/ }));
    expect(onSelect).toHaveBeenCalledWith('momentum_12_1');
  });

  it('shows the loading, error and empty states', () => {
    hooks.useEdges.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<EdgeList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('Loading edges…')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<EdgeList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('The edges failed to load.')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery([]));
    rerender(<EdgeList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('No edge is declared.')).toBeInTheDocument();
  });
});
