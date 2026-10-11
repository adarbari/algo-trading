import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EDGES_FIXTURE } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { EdgePage } from './EdgePage';

const hooks = vi.hoisted(() => ({ useEdges: vi.fn(), useEdgeLiveStates: vi.fn() }));

vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdges: hooks.useEdges,
  useEdgeLiveStates: hooks.useEdgeLiveStates,
}));
vi.mock('@/widgets/edge-detail', async () => {
  const { Button, Text } = await import('@algotrade/ui');
  return {
    EdgeHeader: ({ edge, onBack }: { edge: { id: string }; onBack: () => void }) => (
      <Button onClick={onBack}>{`header ${edge.id}`}</Button>
    ),
    EdgeCompare: ({ edgeId }: { edgeId: string }) => <Text>{`compare ${edgeId}`}</Text>,
    EdgeDefinition: ({ edge }: { edge: { id: string } }) => <Text>{`definition ${edge.id}`}</Text>,
    EdgeDetails: ({ edge }: { edge: { id: string } }) => <Text>{`details ${edge.id}`}</Text>,
    EdgeLive: ({ edgeId }: { edgeId: string }) => <Text>{`live ${edgeId}`}</Text>,
  };
});
vi.mock('@/widgets/edge-evidence', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EdgeEvidence: ({ edgeId }: { edgeId: string }) => <Text>{`evidence ${edgeId}`}</Text> };
});
vi.mock('@/widgets/edge-sureness', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EdgeSureness: ({ edgeId }: { edgeId: string }) => <Text>{`sureness ${edgeId}`}</Text> };
});
vi.mock('@/widgets/edge-performance', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    EdgePerformance: ({ edgeId }: { edgeId: string }) => <Text>{`performance ${edgeId}`}</Text>,
  };
});

const live = (state: string, edgeId = 'momentum_12_1') => ({ edgeId, state });

beforeEach(() => {
  hooks.useEdges.mockReturnValue(fakeQuery(EDGES_FIXTURE.edges));
  hooks.useEdgeLiveStates.mockReturnValue(fakeQuery([live('on_track')]));
});

const page = (id = 'momentum_12_1') =>
  render(<EdgePage id={id} onBack={vi.fn()} onEdit={vi.fn()} />);

describe('EdgePage', () => {
  it('composes the head and the sections in reading order, with a navigation to each', async () => {
    const { container } = page();
    expect(screen.getByText('header momentum_12_1')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Sections of this edge' });
    expect(Array.from(nav.querySelectorAll('a')).map((a) => a.textContent)).toEqual([
      'Evidence',
      'How sure',
      'Where it worked',
      'Live record',
      'Definition',
      'Details',
    ]);
    const order = [
      'evidence momentum_12_1',
      'sureness momentum_12_1',
      'performance momentum_12_1',
      'live momentum_12_1',
      'definition momentum_12_1',
      'details momentum_12_1',
    ];
    const found = await Promise.all(order.map((text) => screen.findByText(text)));
    found.slice(1).forEach((node, i) => {
      const before = found.at(i);
      expect(before?.compareDocumentPosition(node)).toBeTruthy();
      expect((before?.compareDocumentPosition(node) ?? 0) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      );
    });
    for (const id of ['evidence', 'sure', 'where', 'live', 'definition', 'details']) {
      expect(container.querySelector(`#edge-${id}`)).toBeInTheDocument(); // what the navigation scrolls to
    }
    await expectNoA11yViolations(container);
  });

  it('leaves the live record out until the edge has one, and the comparison out of a site edge', async () => {
    hooks.useEdgeLiveStates.mockReturnValue(fakeQuery([live('no_trades')]));
    page();
    await screen.findByText('details momentum_12_1');
    expect(screen.queryByRole('link', { name: 'Live record' })).not.toBeInTheDocument();
    expect(screen.queryByText(/^live /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^compare /)).not.toBeInTheDocument();
  });

  it("shows a copy's comparison", async () => {
    page('my_momentum');
    expect(await screen.findByText('compare my_momentum')).toBeInTheDocument();
  });

  it('offers the way back from the head', async () => {
    const onBack = vi.fn();
    render(<EdgePage id="momentum_12_1" onBack={onBack} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'header momentum_12_1' }));
    expect(onBack).toHaveBeenCalled();
  });

  it('says when the chosen edge does not exist, and shows loading and error with a retry', async () => {
    const { rerender } = page('nope');
    expect(screen.getByText('No edge nope')).toBeInTheDocument();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined));
    rerender(<EdgePage id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText('Loading edge')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdges.mockReturnValue(failed);
    rerender(<EdgePage id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
