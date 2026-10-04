import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import { PreviewResults } from './PreviewResults';

const state = vi.hoisted(() => ({ preview: {} }));

vi.mock('@/features/screener-builder', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerBuilder: () => ({ preview: state.preview }),
}));

const row = (
  rank: number,
  symbol: string,
  decision: string,
  score: number,
  columns: Record<string, unknown> = {},
) => ({
  instrument_id: `EQ:${symbol}`,
  symbol,
  rank,
  decision,
  score,
  columns,
  flags: rank === 1 ? ['leveraged'] : [],
  reasons: decision === 'WATCH' ? ['spread within tolerance'] : [],
});
const DATA = {
  session: '2026-10-02',
  total: 4203,
  decisions: { QUALIFIED: 2, WATCH: 1, REJECT: 100 },
  rows: [
    row(1, 'AAPL', 'QUALIFIED', 92, { next_earnings: '2026-10-29' }),
    row(2, 'MSFT', 'QUALIFIED', 88),
    row(3, 'KO', 'WATCH', 79),
  ],
};

stubElementSize();

beforeEach(() => {
  state.preview = { data: DATA, pending: false, error: null, idle: false };
});

describe('PreviewResults', () => {
  it('lists the top rows with decision counts in the title and the screen columns', async () => {
    const { container } = render(<PreviewResults onOpen={vi.fn()} />);
    expect(
      screen.getByRole('heading', { name: 'Preview · 2 qualified · 1 watch' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Top 3 of 4,203 on 2026-10-02')).toBeInTheDocument();
    const grid = screen.getByRole('grid', { name: 'Preview results' });
    expect(grid).toHaveTextContent('next earnings');
    expect(screen.getByRole('row', { name: /AAPL/ })).toHaveTextContent('leveraged');
    expect(screen.getByRole('row', { name: /KO/ })).toHaveTextContent('spread within tolerance');
    await expectNoA11yViolations(container);
  });

  it('filters by decision and opens a ticker', async () => {
    const onOpen = vi.fn();
    render(<PreviewResults onOpen={onOpen} />);
    await userEvent.click(screen.getByRole('button', { name: 'Watch' }));
    expect(screen.queryByRole('row', { name: /AAPL/ })).toBeNull();
    await userEvent.click(screen.getByText('KO'));
    expect(onOpen).toHaveBeenCalledWith('KO');
  });

  it('asks for a complete criterion while idle', () => {
    state.preview = { data: undefined, pending: false, error: null, idle: true };
    render(<PreviewResults onOpen={vi.fn()} />);
    expect(
      screen.getByText('Add a complete criterion to preview what it would pick.'),
    ).toBeInTheDocument();
  });
});
