import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EDGES_FIXTURE } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { EdgePage } from './EdgePage';

const hooks = vi.hoisted(() => ({ useEdge: vi.fn(), useEdgeLiveStates: vi.fn() }));

vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdge: hooks.useEdge,
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
    EdgeDetails: ({ edge, children }: { edge: { id: string }; children?: ReactNode }) => (
      <>
        <Text>{`details ${edge.id}`}</Text>
        {children}
      </>
    ),
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
vi.mock('@/widgets/edge-diagnostics', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    EdgeDiagnostics: ({ edgeId }: { edgeId: string }) => <Text>{`diagnostics ${edgeId}`}</Text>,
  };
});
vi.mock('@/widgets/edge-trades', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EdgeTrades: ({ edgeId }: { edgeId: string }) => <Text>{`trades ${edgeId}`}</Text> };
});
vi.mock('@/widgets/edge-performance', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    EdgePerformance: ({ edgeId }: { edgeId: string }) => <Text>{`performance ${edgeId}`}</Text>,
  };
});

const live = (state: string, edgeId = 'momentum_12_1') => ({ edgeId, state });

beforeEach(() => {
  hooks.useEdge.mockImplementation((id: string) =>
    fakeQuery(EDGES_FIXTURE.edges.find((e) => e.id === id) ?? null),
  );
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
      'Trades',
      'Definition',
      'Details',
    ]);
    const order = [
      'evidence momentum_12_1',
      'sureness momentum_12_1',
      'performance momentum_12_1',
      'live momentum_12_1',
      'trades momentum_12_1',
      'definition momentum_12_1',
      'details momentum_12_1',
      'diagnostics momentum_12_1',
    ];
    const found = await Promise.all(order.map((text) => screen.findByText(text)));
    found.slice(1).forEach((node, i) => {
      const before = found.at(i);
      expect(before?.compareDocumentPosition(node)).toBeTruthy();
      expect((before?.compareDocumentPosition(node) ?? 0) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      );
    });
    for (const id of ['evidence', 'sure', 'where', 'live', 'trades', 'definition', 'details']) {
      expect(container.querySelector(`#edge-${id}`)).toBeInTheDocument(); // what the navigation scrolls to
    }
    await expectNoA11yViolations(container);
  });

  it('keeps the live record section for an edge that records nothing, and the comparison out of a site edge', async () => {
    hooks.useEdgeLiveStates.mockReturnValue(fakeQuery([live('not_recording')]));
    page();
    await screen.findByText('details momentum_12_1');
    expect(screen.getByRole('link', { name: 'Live record' })).toBeInTheDocument();
    expect(await screen.findByText('live momentum_12_1')).toBeInTheDocument();
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

  it('reads only the chosen edge, never the list', () => {
    page();
    expect(hooks.useEdge).toHaveBeenCalledWith('momentum_12_1');
  });

  it('says when the chosen edge does not exist, and shows loading and error with a retry', async () => {
    const { rerender } = page('nope');
    expect(screen.getByText('No edge nope')).toBeInTheDocument();
    hooks.useEdge.mockReturnValue(fakeQuery(undefined));
    rerender(<EdgePage id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText('Loading edge')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdge.mockReturnValue(failed);
    rerender(<EdgePage id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
