import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeLive } from './EdgeLive';

const hooks = vi.hoisted(() => ({ useEdgePaper: vi.fn() }));
vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdgePaper: hooks.useEdgePaper,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

stubElementSize();

const RECORD = {
  state: 'on_track',
  closed: 20,
  wins: 12,
  open: 2,
  skipped: 1,
  winRate: 0.6,
  backtestRate: 0.62,
  basis: 'out-of-sample win rate',
  low: 0.4,
  high: 0.8,
  headline: '12 of 20 closed trades won (60%), inside the usual range of 40% to 80%.',
  bins: [
    { start: 0, end: 0.5, chance: 0.3 },
    { start: 0.5, end: 1, chance: 0.7 },
  ],
};
const TRADES = [
  {
    instrumentId: 'EQ:A',
    instrument: { symbol: 'AAA' },
    rank: 1,
    signalSession: '2026-09-02',
    buySession: '2026-09-03',
    sellSession: '2026-10-01',
    status: 'won',
    reason: '',
    excessReturn: 0.023,
  },
  {
    instrumentId: 'EQ:B',
    instrument: null,
    rank: 2,
    signalSession: '2026-09-02',
    buySession: '2026-09-03',
    sellSession: '2026-10-01',
    status: 'skipped',
    reason: 'no entry bar at the buy session',
    excessReturn: null,
  },
];
const paper = (over: Record<string, unknown> = {}) => ({
  edgeId: 'drift',
  record: RECORD,
  trades: TRADES,
  forward: null,
  ...over,
});

beforeEach(() => {
  hooks.useEdgePaper.mockReset();
});

describe('EdgeLive', () => {
  it('shows the record against the usual range, the picture and the paper trades', async () => {
    hooks.useEdgePaper.mockReturnValue(fakeQuery(paper()));
    const { container } = render(<EdgeLive edgeId="drift" />);
    expect(screen.getByText('On track')).toBeVisible();
    expect(screen.getByText(RECORD.headline)).toBeVisible();
    const strip = screen.getByRole('region', { name: 'Live record figures' });
    expect(within(strip).getByText('60%')).toBeVisible();
    expect(within(strip).getByText('out-of-sample win rate')).toBeVisible();
    expect(
      screen.getByRole('img', { name: /Chance of each win rate if the backtest held/ }),
    ).toBeVisible();
    const trades = screen.getByRole('grid', { name: 'Paper trades' });
    expect(within(trades).getByText('AAA')).toBeVisible();
    expect(within(trades).getByText('Won')).toBeVisible();
    expect(within(trades).getByText('+2.3%')).toBeVisible();
    expect(within(trades).getByText('Skipped')).toBeVisible();
    expect(screen.getByText('help usual_range')).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it("shows a new version's forward test beside the edge it would replace", () => {
    hooks.useEdgePaper.mockReturnValue(
      fakeQuery(
        paper({
          forward: {
            replaces: 'drift',
            replacesName: 'Drift',
            since: '2026-09-01',
            sessions: 24,
            needed: 20,
            canReplace: true,
            headline: 'It can replace the edge.',
            this: { closed: 10, wins: 7, winRate: 0.7 },
            replaced: { closed: 10, wins: 5, winRate: 0.5 },
          },
        }),
      ),
    );
    render(<EdgeLive edgeId="drift2" />);
    expect(screen.getByText('It can replace the edge.')).toBeVisible();
    const strip = screen.getByRole('region', { name: 'Forward test figures' });
    expect(within(strip).getByText('70%')).toBeVisible();
    expect(within(strip).getByText('50%')).toBeVisible();
    expect(within(strip).getByText('of 20')).toBeVisible();
    expect(screen.getByText('help forward_test')).toBeVisible();
  });

  it('shows no picture before there is a range and nothing without trades or a forward test', () => {
    hooks.useEdgePaper.mockReturnValue(
      fakeQuery(
        paper({ record: { ...RECORD, state: 'too_early', bins: [], low: null, high: null } }),
      ),
    );
    const { container, rerender } = render(<EdgeLive edgeId="drift" />);
    expect(screen.getByText('Too early to judge')).toBeVisible();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    hooks.useEdgePaper.mockReturnValue(
      fakeQuery(paper({ record: { ...RECORD, state: 'no_trades' }, trades: [] })),
    );
    rerender(<EdgeLive edgeId="drift" />);
    expect(container).toBeEmptyDOMElement();
    hooks.useEdgePaper.mockReturnValue(fakeQuery(null));
    rerender(<EdgeLive edgeId="drift" />);
    expect(container).toBeEmptyDOMElement();
  });
});
