import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeSignals } from './EdgeSignals';

const hooks = vi.hoisted(() => ({ useEdgeDesk: vi.fn(), useEdgeLiveStates: vi.fn() }));
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdgeDesk: hooks.useEdgeDesk,
  useEdgeLiveStates: hooks.useEdgeLiveStates,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text>,
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
  };
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
  hooks.useEdgeLiveStates.mockReset();
  hooks.useEdgeLiveStates.mockReturnValue(fakeQuery([]));
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

  it('warns for every edge below its usual range, followed or the site, with its sentence', async () => {
    const states = [
      { edgeId: 'drift', name: 'Drift', state: 'below', closed: 20, winRate: 0.2, followed: true },
      {
        edgeId: 'site2',
        name: 'Site two',
        state: 'below',
        closed: 30,
        winRate: 0.3,
        followed: false,
      },
      { edgeId: 'ok', name: 'Fine', state: 'on_track', closed: 20, winRate: 0.6, followed: true },
    ].map((s) => ({ ...s, headline: `${s.name}: 4 of 20 closed trades won.` }));
    hooks.useEdgeLiveStates.mockReturnValue(fakeQuery(states));
    hooks.useEdgeDesk.mockReturnValue(fakeQuery({ ...DESK, buys: [], sells: [], followed: [] }));
    const h = handlers();
    const { container } = render(<EdgeSignals {...h} />);
    expect(screen.getByText('Drift: below range')).toBeVisible();
    expect(screen.getByText('Site two: below range')).toBeVisible();
    expect(screen.getByText('Drift: 4 of 20 closed trades won.')).toBeVisible();
    expect(screen.queryByText(/Fine: below/)).not.toBeInTheDocument();
    expect(screen.getAllByText('help live_state')).toHaveLength(2);
    await userEvent
      .setup()
      .click(screen.getAllByRole('button', { name: 'Open edge' }).at(1) as HTMLElement);
    expect(h.onOpenEdge).toHaveBeenCalledWith('site2');
    await expectNoA11yViolations(container);
  });

  it('shows no banner while every edge is on track', () => {
    hooks.useEdgeDesk.mockReturnValue(fakeQuery(DESK));
    render(<EdgeSignals {...handlers()} />);
    expect(screen.queryByRole('button', { name: 'Open edge' })).not.toBeInTheDocument();
  });
});
