import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { ScreenerHitsPanel } from './ScreenerHitsPanel';

const hooks = vi.hoisted(() => ({ useScreenerHits: vi.fn() }));

vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerHits: hooks.useScreenerHits,
}));

const hit = (id: string, name: string, decision: string, score: number | null) => ({
  screener: { id, name },
  result: { rank: 2, decision, score, reasons: 'iv rank near', flags: [], change: 'new' },
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
  it('lists the screeners that picked the ticker, with what their run stored', async () => {
    const { container } = render(<ScreenerHitsPanel symbol="AAPL" />);
    expect(hooks.useScreenerHits).toHaveBeenCalledWith('AAPL');
    const list = screen.getByLabelText('Screeners that picked AAPL');
    expect(list).toHaveTextContent('VRP scanner');
    expect(list).toHaveTextContent('#2 · score 72 · new · iv rank near');
    expect(list).toHaveTextContent('Watch');
    expect(list).toHaveTextContent('Qualified');
    expect(screen.getByText('Session 2026-10-02')).toBeInTheDocument();
    await expectNoA11yViolations(container);
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
