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
const { stub } = vi.hoisted(() => ({
  stub: (name: string, label: string) => async () => {
    const { Text } = await import('@algotrade/ui');
    return {
      [name]: ({ edgeId, edge }: { edgeId?: string; edge?: { id: string } }) => (
        <Text>{`${label} ${edgeId ?? edge?.id ?? ''}`}</Text>
      ),
    };
  },
}));

vi.mock('@/widgets/setup-head', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    EdgeHeader: ({ edge, onBack }: { edge: { id: string }; onBack: () => void }) => (
      <Button onClick={onBack}>{`header ${edge.id}`}</Button>
    ),
  };
});
vi.mock('@/widgets/setup-rules', stub('SetupRules', 'rules'));
vi.mock('@/widgets/setup-record', stub('SetupRecord', 'record'));
vi.mock('@/widgets/setup-fails', stub('SetupFails', 'fails'));
vi.mock('@/widgets/setup-checklist', async () => {
  const { Text } = await import('@algotrade/ui');
  return { BeforeYouAct: () => <Text>before</Text> };
});
vi.mock('@/widgets/setup-deeper', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    SetupDeeper: ({ edge, children }: { edge: { id: string }; children?: ReactNode }) => (
      <>
        <Text>{`deeper ${edge.id}`}</Text>
        {children}
      </>
    ),
  };
});
vi.mock('@/widgets/edge-diagnostics', stub('EdgeDiagnostics', 'diagnostics'));
vi.mock('@/widgets/edge-trades', stub('EdgeTrades', 'trades'));

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
    const nav = screen.getByRole('navigation', { name: 'Sections of this setup' });
    expect(Array.from(nav.querySelectorAll('a')).map((a) => a.textContent)).toEqual([
      'The rules',
      'How it has done',
      'When it fails',
      'Before you act',
      'Dig deeper',
    ]);
    const order = [
      'rules momentum_12_1',
      'record momentum_12_1',
      'fails momentum_12_1',
      'before',
      'deeper momentum_12_1',
      'trades momentum_12_1',
      'diagnostics momentum_12_1',
    ];
    const found = await Promise.all(order.map((text) => screen.findByText(text)));
    found.slice(1).forEach((node, i) => {
      const before = found.at(i);
      expect((before?.compareDocumentPosition(node) ?? 0) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      );
    });
    for (const id of ['rules', 'record', 'fails', 'before', 'deeper']) {
      expect(container.querySelector(`#setup-${id}`)).toBeInTheDocument(); // what the navigation scrolls to
    }
    await expectNoA11yViolations(container);
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
    expect(screen.getByText('No setup nope')).toBeInTheDocument();
    hooks.useEdge.mockReturnValue(fakeQuery(undefined));
    rerender(<EdgePage id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText('Loading setup')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdge.mockReturnValue(failed);
    rerender(<EdgePage id="momentum_12_1" onBack={vi.fn()} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
