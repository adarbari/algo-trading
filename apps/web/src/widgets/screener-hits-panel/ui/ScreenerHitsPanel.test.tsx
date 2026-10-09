import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { ScreenerHitsPanel } from './ScreenerHitsPanel';

const hooks = vi.hoisted(() => ({ useScreenerHits: vi.fn() }));

vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerHits: hooks.useScreenerHits,
  CriteriaScorecard: (props: { screenerId: string; label?: string }) => (
    <Text>{`scorecard of ${props.screenerId}`}</Text>
  ),
}));

const hit = (id: string, name: string, decision: string, score: number | null) => ({
  screener: { id, name },
  result: {
    rank: 2,
    decision,
    score,
    reasons: 'iv rank near',
    flags: [],
    change: 'new',
    criteria: [],
  },
});

beforeEach(() => {
  hooks.useScreenerHits.mockReturnValue(
    fakeQuery({
      session: '2026-10-02',
      hits: [hit('vrp', 'VRP scanner', 'WATCH', 72.4), hit('mine', 'Mine', 'QUALIFIED', null)],
    }),
  );
});

describe('ScreenerHitsPanel', () => {
  it("opens a screener's results from its open row when given the callback", async () => {
    const onOpenScreener = vi.fn();
    render(<ScreenerHitsPanel symbol="AAPL" onOpenScreener={onOpenScreener} via="vrp" />);
    await userEvent.click(screen.getByRole('button', { name: 'Open VRP scanner' }));
    expect(onOpenScreener).toHaveBeenCalledWith('vrp');
  });

  it('lists the screeners that picked the ticker, each with its decision, rank and score', async () => {
    const { container } = render(<ScreenerHitsPanel symbol="AAPL" />);
    expect(hooks.useScreenerHits).toHaveBeenCalledWith('AAPL');
    const row = screen.getByRole('button', { name: /VRP scanner/ });
    expect(row).toHaveTextContent('Watch');
    expect(row).toHaveTextContent('#2');
    expect(row).toHaveTextContent('score 72');
    expect(screen.getByRole('button', { name: /Mine/ })).toHaveTextContent('Qualified');
    expect(screen.getByText('Session 2026-10-02')).toBeInTheDocument();
    expect(screen.queryByText(/scorecard of/)).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('opens the scorecard of a screener on click, one at a time', async () => {
    render(<ScreenerHitsPanel symbol="AAPL" />);
    await userEvent.click(screen.getByRole('button', { name: /VRP scanner/ }));
    expect(screen.getByText('scorecard of vrp')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Mine/ }));
    expect(screen.queryByText('scorecard of vrp')).toBeNull();
    expect(screen.getByText('scorecard of mine')).toBeInTheDocument();
  });

  it('opens the screener the reader came from (via) first', () => {
    render(<ScreenerHitsPanel symbol="AAPL" via="mine" />);
    expect(screen.getByText('scorecard of mine')).toBeInTheDocument();
    expect(screen.queryByText('scorecard of vrp')).toBeNull();
  });

  it('says when none picked it, or the ticker is unknown', () => {
    hooks.useScreenerHits.mockReturnValue(fakeQuery({ session: '2026-10-02', hits: [] }));
    const { rerender } = render(<ScreenerHitsPanel symbol="KO" />);
    expect(
      screen.getByText('None of your screeners picked KO in the session 2026-10-02.'),
    ).toBeInTheDocument();
    hooks.useScreenerHits.mockReturnValue(fakeQuery(null));
    rerender(<ScreenerHitsPanel symbol="ZZZ" />);
    expect(screen.getByText('ZZZ is not in the reference snapshot.')).toBeInTheDocument();
  });
});
