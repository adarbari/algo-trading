import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { EtfHoldings } from '@/entities/holdings';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { HoldingsPanel } from './HoldingsPanel';

const hooks = vi.hoisted(() => ({ useEtfHoldings: vi.fn() }));

vi.mock('@/entities/holdings', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEtfHoldings: hooks.useEtfHoldings,
}));

stubElementSize();

const HOLDINGS: EtfHoldings = {
  instrument_id: 'EQ:XLK',
  is_etf: true,
  as_of: '2026-10-01',
  source: 'ssga_holdings',
  total: 77,
  items: [
    {
      rank: 1,
      name: 'NVIDIA CORP',
      symbol: 'NVDA',
      instrument_id: 'EQ:NVDA',
      weight: 0.154706,
      asset_class: 'Equity',
    },
    {
      rank: 2,
      name: 'ASML HOLDING NV',
      symbol: 'ASML',
      instrument_id: null,
      weight: 0.0209,
      asset_class: 'Equity',
    },
    {
      rank: 3,
      name: 'U.S. Dollar',
      symbol: null,
      instrument_id: null,
      weight: 0.0087,
      asset_class: 'Cash',
    },
  ],
};

beforeEach(() => {
  hooks.useEtfHoldings.mockReturnValue(fakeQuery(HOLDINGS));
});

describe('HoldingsPanel', () => {
  it('lists the top holdings with their weights, the total, the date and the source', async () => {
    const { container } = render(<HoldingsPanel symbol="XLK" />);
    expect(hooks.useEtfHoldings).toHaveBeenCalledWith('XLK', 10);
    expect(
      screen.getByText('Top 3 of 77 holdings · 18.4% of the fund · as of 1 Oct 2026'),
    ).toBeInTheDocument();
    const grid = screen.getByRole('grid', { name: 'XLK top holdings' });
    const rows = within(grid).getAllByRole('row').slice(1);
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining('1NVIDIA CORPNVDA15.47%Equity'),
      expect.stringContaining('2ASML HOLDING NVASML2.09%Equity'),
      expect.stringContaining('3U.S. Dollar0.87%Cash'),
    ]);
    expect(screen.getByText('Source: State Street daily holdings file.')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('opens the row of a holding that is in the universe, and only that one', async () => {
    const onSelectSymbol = vi.fn();
    render(<HoldingsPanel symbol="XLK" onSelectSymbol={onSelectSymbol} />);
    await userEvent.click(screen.getByText('NVIDIA CORP'));
    expect(onSelectSymbol).toHaveBeenCalledExactlyOnceWith('NVDA');
    onSelectSymbol.mockClear();
    // ASML has a ticker but is not in the universe; cash has none: neither opens anything.
    await userEvent.click(screen.getByText('ASML HOLDING NV'));
    await userEvent.click(screen.getByText('U.S. Dollar'));
    expect(onSelectSymbol).not.toHaveBeenCalled();
  });

  it('opens the active row with Enter from the keyboard', async () => {
    const onSelectSymbol = vi.fn();
    render(<HoldingsPanel symbol="XLK" onSelectSymbol={onSelectSymbol} />);
    screen.getByRole('grid', { name: 'XLK top holdings' }).focus();
    await userEvent.keyboard('{Enter}');
    expect(onSelectSymbol).toHaveBeenCalledExactlyOnceWith('NVDA');
  });

  it('says so when the fund has no stored holdings', () => {
    hooks.useEtfHoldings.mockReturnValue(
      fakeQuery({ ...HOLDINGS, as_of: null, source: null, total: 0, items: [] }),
    );
    render(<HoldingsPanel symbol="GLD" />);
    expect(screen.getByText(/No holdings stored for GLD/)).toBeInTheDocument();
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  });

  it('counts a short line by its size and says so, for an inverse fund', () => {
    hooks.useEtfHoldings.mockReturnValue(
      fakeQuery({
        ...HOLDINGS,
        items: [
          {
            rank: 1,
            name: 'Total Return Swap',
            symbol: null,
            instrument_id: null,
            weight: -0.8,
            asset_class: 'Derivative',
          },
          {
            rank: 2,
            name: 'T-Bill',
            symbol: null,
            instrument_id: null,
            weight: 0.1,
            asset_class: 'Cash',
          },
        ],
      }),
    );
    render(<HoldingsPanel symbol="SQQQ" />);
    expect(
      screen.getByText(/90\.0% of the fund by size, short lines included/),
    ).toBeInTheDocument();
  });

  it('says a non-ETF is not an ETF rather than that nothing is stored', () => {
    hooks.useEtfHoldings.mockReturnValue(
      fakeQuery({ ...HOLDINGS, is_etf: false, as_of: null, source: null, total: 0, items: [] }),
    );
    render(<HoldingsPanel symbol="AAPL" />);
    expect(screen.getByText('AAPL is not an ETF, so it has no holdings.')).toBeInTheDocument();
  });

  it('shows the table loading, and an error with a retry', async () => {
    hooks.useEtfHoldings.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<HoldingsPanel symbol="XLK" />);
    expect(screen.getByRole('grid', { name: 'XLK top holdings' })).toHaveAttribute(
      'aria-busy',
      'true',
    );
    const query = fakeQuery(undefined, { isError: true });
    hooks.useEtfHoldings.mockReturnValue(query);
    rerender(<HoldingsPanel symbol="XLK" />);
    expect(screen.getByText('XLK holdings failed to load.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(query.refetch).toHaveBeenCalled();
  });
});
