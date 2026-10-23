import { IconButton } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScreenerEdge } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { ScreenerEdgeLine } from './ScreenerEdgeLine';

const hooks = vi.hoisted(() => ({ useScreenerEdges: vi.fn() }));

vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerEdges: hooks.useScreenerEdges,
}));
// The help button reads the Guide; its own test covers that.
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => <IconButton icon="info" label={`Help: ${id}`} />,
}));

const edge = (edgeId: string, status: string, trades: number | null): ScreenerEdge => ({
  edgeId,
  edgeName: `Edge ${edgeId}`,
  status,
  frozenSince: '2026-04-01',
  runLabel: `${edgeId} run`,
  figures:
    trades === null
      ? null
      : { hitRate: 0.62, baseRate: 0.55, liftPts: 7, trades, picks: 400, horizonSessions: 20 },
  notRun:
    trades === null
      ? { code: 'NOT_RUN', kind: 'NOT_RUN', guideTerm: 'not_run', kindText: 'not run yet' }
      : null,
});

function setup(edges: ScreenerEdge[] | 'pending' | 'error') {
  hooks.useScreenerEdges.mockReturnValue(
    edges === 'pending'
      ? fakeQuery(undefined, { isPending: true })
      : edges === 'error'
        ? fakeQuery(undefined, { isError: true })
        : fakeQuery(edges),
  );
  const onOpenEdge = vi.fn();
  const view = render(<ScreenerEdgeLine screenerId="vrp" onOpenEdge={onOpenEdge} />);
  return { onOpenEdge, ...view };
}

describe('ScreenerEdgeLine', () => {
  beforeEach(() => {
    hooks.useScreenerEdges.mockReset();
  });

  it('shows the headline edge with its status, win rate against the base rate, trades and hold', async () => {
    const { container } = setup([edge('a', 'evidenced', 40)]);
    expect(screen.getByText('Edge a')).toBeInTheDocument();
    expect(screen.getByText('Evidenced')).toBeInTheDocument();
    expect(screen.getByText(/62\.0%/)).toBeInTheDocument();
    expect(screen.getByText(/55\.0%/)).toBeInTheDocument();
    expect(screen.getByText(/20-session hold · frozen period since/)).toBeInTheDocument();
    expect(screen.queryByText(/\+\d edge/)).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('chips the other edges and opens each edge’s record under Evidence', async () => {
    const { onOpenEdge } = setup([edge('a', 'evidenced', 40), edge('b', 'candidate', 90)]);
    expect(screen.getByText('+1 edge')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edge b' })).toBeNull();
    const control = screen.getByRole('button', { name: 'Evidence' });
    expect(control).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(control);
    expect(control).toHaveAttribute('aria-expanded', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Edge b' }));
    expect(onOpenEdge).toHaveBeenCalledWith('b');
  });

  it('says an edge with no record yet in the server’s words', () => {
    setup([edge('a', 'candidate', null)]);
    expect(screen.getByText('No record yet: not run yet')).toBeInTheDocument();
  });

  it('says a screener no edge lists is not part of one', () => {
    setup([]);
    expect(screen.getByText(/Not part of an edge/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Evidence' })).toBeNull();
  });

  it('shows a placeholder while loading and says when the read failed', () => {
    const { unmount } = setup('pending');
    expect(screen.getByText("Loading the screener's edge…")).toBeInTheDocument();
    unmount();
    setup('error');
    expect(screen.getByText('The edge record failed to load.')).toBeInTheDocument();
  });
});
