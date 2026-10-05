import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { OverviewPanel } from './OverviewPanel';

const hooks = vi.hoisted(() => ({ useInstrument: vi.fn(), useInstrumentEvents: vi.fn() }));

vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrument: hooks.useInstrument,
  useInstrumentEvents: hooks.useInstrumentEvents,
}));

const stock = {
  instrument_id: 'EQ:KO',
  reference_snapshot: '2026-10-02',
  reference: { name: 'Coca-Cola', security_type: 'COMMON_STOCK', is_etf: false, exchange: 'NYSE' },
  company: {
    name: 'Coca-Cola Co',
    sector: 'Consumer Staples',
    industry: 'Beverages',
    description: 'Makes and sells non-alcoholic beverages worldwide.',
  },
  features: {
    'rollup.price_stats@v2.close': 74.1,
    'feature.market_cap': 3.2e11,
    'feature.pe_ratio': 24.3,
    'rollup.financials@v1.revenue_ttm': 4.7e10,
    'rollup.dividends@v2.last_ex_date': '2026-09-12',
  },
  feature_sessions: {},
};

beforeEach(() => {
  hooks.useInstrument.mockReturnValue(fakeQuery(stock));
  hooks.useInstrumentEvents.mockReturnValue(
    fakeQuery([
      {
        table: 'events/earnings',
        ts: '2099-02-10T00:00:00+00:00',
        values: { reported: false, eps_forecast: 0.8 },
      },
    ]),
  );
});

describe('OverviewPanel', () => {
  it('says what the company is, its sector and the key numbers', async () => {
    const { container } = render(<OverviewPanel symbol="KO" />);
    expect(screen.getByRole('heading', { name: 'KO · overview' })).toBeInTheDocument();
    expect(screen.getByText('Coca-Cola Co')).toBeInTheDocument();
    expect(screen.getByText('Consumer Staples')).toBeInTheDocument();
    expect(screen.getByText('Beverages')).toBeInTheDocument();
    expect(screen.getByText('Makes and sells non-alcoholic beverages worldwide.')).toBeVisible();
    const strip = screen.getByRole('region', { name: 'KO headline numbers' });
    expect(strip).toHaveTextContent('P/E ratio24.3');
    expect(strip).toHaveTextContent('Revenue (TTM)$47B');
    expect(strip).toHaveTextContent('Next earnings10 Feb 2099');
    await expectNoA11yViolations(container);
  });

  it('says so when there is no description, and shows no fund section for a stock', () => {
    hooks.useInstrument.mockReturnValue(fakeQuery({ ...stock, company: { name: 'Coca-Cola Co' } }));
    render(<OverviewPanel symbol="KO" fund={<Text>holdings</Text>} />);
    expect(screen.getByText('No description stored for KO yet.')).toBeInTheDocument();
    expect(screen.queryByText('holdings')).not.toBeInTheDocument();
  });

  it('shows the fund section for an ETF', () => {
    hooks.useInstrument.mockReturnValue(
      fakeQuery({
        ...stock,
        reference: { name: 'SPDR S&P 500', security_type: 'ETF', is_etf: true },
        company: null,
      }),
    );
    render(<OverviewPanel symbol="SPY" fund={<Text>holdings</Text>} />);
    expect(screen.getByText('holdings')).toBeInTheDocument();
  });

  it('shows an error with a retry when the detail fails', () => {
    hooks.useInstrument.mockReturnValue(fakeQuery(undefined, { isError: true }));
    render(<OverviewPanel symbol="KO" />);
    expect(screen.getByText('KO failed to load.')).toBeInTheDocument();
  });
});
