import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeSignals } from './EdgeSignals';

const hooks = vi.hoisted(() => ({ useEdgeDesk: vi.fn() }));
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdgeDesk: hooks.useEdgeDesk,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

stubElementSize();

const trade = (symbol: string | null, rank: number, edgeId = 'drift') => ({
  edgeId,
  edgeName: 'Drift',
  instrumentId: `EQ:${symbol ?? 'X'}`,
  instrument: symbol ? { symbol } : null,
  rank,
  buySession: '2026-10-06',
  sellSession: '2026-11-03',
});
const DESK = {
  session: '2026-10-05',
  sellSession: '2026-10-06',
  buys: [trade('AAA', 1), trade(null, 2)],
  sells: [trade('OLD', 1)],
  followed: [
    {
      edgeId: 'drift',
      name: 'Drift',
      state: 'following',
      tonight: 'skipped',
      tonightReason: 'no features for 2026-10-05',
      missed: ['2026-10-01'],
      record: { state: 'on_track', closed: 20, open: 3, winRate: 0.6 },
    },
  ],
};

beforeEach(() => {
  hooks.useEdgeDesk.mockReset();
});

const handlers = () => ({ onOpen: vi.fn(), onOpenEdge: vi.fn(), onOpenEdges: vi.fn() });

describe('EdgeSignals', () => {
  it("lists tonight's buys, next session's sells and the followed edges with their record", async () => {
    hooks.useEdgeDesk.mockReturnValue(fakeQuery(DESK));
    const h = handlers();
    const { container } = render(<EdgeSignals {...h} />);
    const buys = screen.getByRole('grid', { name: 'Buy next session' });
    expect(within(buys).getByText('AAA')).toBeVisible();
    expect(within(buys).getByText('EQ:X')).toBeVisible(); // no symbol: the id
    expect(
      within(screen.getByRole('grid', { name: 'Sell next session' })).getByText('OLD'),
    ).toBeVisible();
    const followed = screen.getByRole('grid', { name: 'Followed edges' });
    expect(within(followed).getByText('On track')).toBeVisible();
    expect(within(followed).getByText('Skipped')).toBeVisible();
    expect(within(followed).getByText('no features for 2026-10-05')).toBeVisible();
    expect(screen.getByText('help edge_tonight')).toBeVisible();
    expect(within(buys).getByRole('columnheader', { name: /Buy on/ })).toBeVisible();
    expect(within(followed).getByText('60%')).toBeVisible();
    expect(screen.getByText('help paper_trading')).toBeVisible();
    await userEvent.setup().click(within(buys).getByText('AAA'));
    expect(h.onOpen).toHaveBeenCalledWith('AAA', 'drift');
    await userEvent.setup().click(within(followed).getByText('Drift'));
    expect(h.onOpenEdge).toHaveBeenCalledWith('drift');
    await expectNoA11yViolations(container);
  });

  it('says what to do when no edge is followed, with a way to Edges', async () => {
    hooks.useEdgeDesk.mockReturnValue(fakeQuery({ ...DESK, buys: [], sells: [], followed: [] }));
    const h = handlers();
    render(<EdgeSignals {...h} />);
    await userEvent
      .setup()
      .click(
        screen.getByRole('button', { name: 'Follow an edge to see what it says to buy and sell' }),
      );
    expect(h.onOpenEdges).toHaveBeenCalledOnce();
  });

  it('shows the same line when nothing is stored, a loading panel, and an error with a retry', async () => {
    hooks.useEdgeDesk.mockReturnValue(fakeQuery(null));
    const { rerender } = render(<EdgeSignals {...handlers()} />);
    expect(screen.getByRole('button', { name: /Follow an edge to see/ })).toBeVisible();
    hooks.useEdgeDesk.mockReturnValue(fakeQuery(undefined));
    rerender(<EdgeSignals {...handlers()} />);
    expect(screen.getByText('Loading edge signals…')).toBeVisible();
    const query = fakeQuery(undefined, { isError: true });
    hooks.useEdgeDesk.mockReturnValue(query);
    rerender(<EdgeSignals {...handlers()} />);
    await userEvent.setup().click(screen.getByRole('button', { name: /Retry/ }));
    expect(query.refetch).toHaveBeenCalledOnce();
  });

  it('says so when a followed edge has nothing to buy or sell', () => {
    hooks.useEdgeDesk.mockReturnValue(fakeQuery({ ...DESK, buys: [], sells: [] }));
    render(<EdgeSignals {...handlers()} />);
    expect(screen.getByText('Nothing to buy next session')).toBeVisible();
    expect(screen.getByText('Nothing to sell next session')).toBeVisible();
  });
});
