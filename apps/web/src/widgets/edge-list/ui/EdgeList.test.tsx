import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EDGES_FIXTURE } from '@/entities/edge';
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
  hooks.useEdges.mockReturnValue(fakeQuery(EDGES_FIXTURE.edges));
});

describe('EdgeList', () => {
  it('groups the edges by verdict, best first, each with its screens, result and trades', async () => {
    const { container } = render(<EdgeList onSelect={vi.fn()} />);
    const table = screen.getByRole('grid', { name: 'Edges' });
    const headings = within(table)
      .getAllByRole('rowheader')
      .map((h) => h.textContent);
    expect(headings).toEqual(['Promising · 1', 'Not working · 1', 'Waiting on data · 1']);
    const momentum = within(table).getByRole('row', { name: /Momentum 12-1/ });
    expect(within(momentum).getByText('screen: momentum_12_1')).toBeInTheDocument();
    expect(within(momentum).getByText('Win rate 57% · base rate 52%')).toBeInTheDocument();
    expect(within(momentum).getByText('70')).toBeInTheDocument();
    expect(within(momentum).getByText('Candidate')).toBeInTheDocument();
    const drift = within(table).getByRole('row', { name: /Earnings drift/ });
    expect(within(drift).getByText('screens: pead, pead_volume')).toBeInTheDocument();
    const waiting = within(table).getByRole('row', { name: /S&P 500 index changes/ });
    expect(within(waiting).getByText('no screen yet')).toBeInTheDocument();
    expect(within(waiting).getByText('Rejected')).toBeInTheDocument();
    for (const id of ['verdict', 'edge_status', 'trades', 'out_of_sample']) {
      expect(screen.getByText(`help ${id}`)).toBeInTheDocument();
    }
    await expectNoA11yViolations(container);
  });

  it('opens an edge on a row click', async () => {
    const onSelect = vi.fn();
    render(<EdgeList onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('row', { name: /Momentum 12-1/ }));
    expect(onSelect).toHaveBeenCalledWith('momentum_12_1');
  });

  it('shows the loading, error and empty states', () => {
    hooks.useEdges.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<EdgeList onSelect={vi.fn()} />);
    expect(screen.getByText('Loading edges…')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<EdgeList onSelect={vi.fn()} />);
    expect(screen.getByText('The edges failed to load.')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery([]));
    rerender(<EdgeList onSelect={vi.fn()} />);
    expect(screen.getByText('No edge is declared.')).toBeInTheDocument();
  });
});
