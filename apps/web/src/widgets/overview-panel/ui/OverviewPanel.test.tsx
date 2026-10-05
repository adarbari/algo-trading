import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { OverviewPanel } from './OverviewPanel';

const hooks = vi.hoisted(() => ({ useInstrumentFacts: vi.fn(), useInstrumentEvents: vi.fn() }));

vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrumentFacts: hooks.useInstrumentFacts,
  useInstrumentEvents: hooks.useInstrumentEvents,
}));

const info = (format: string, unit: string | null = null) => ({
  format,
  unit,
  dtype: 'float',
  nullMeaning: 'no report date on or after the session in the calendars stored by then',
});
const value = (name: string, v: unknown, format: string, unit: string | null = null) => ({
  name,
  value: v,
  unknown: null,
  info: info(format, unit),
});

const session = {
  date: '2026-10-02',
  isLatest: true,
  missing: [],
  referenceSnapshot: '2026-10-02',
  preSnapshot: false,
};

const stock = {
  instrumentId: 'EQ:KO',
  symbol: 'KO',
  name: 'Coca-Cola Co',
  securityType: 'COMMON_STOCK',
  exchange: 'NYSE',
  isEtf: false,
  description: 'Makes and sells non-alcoholic beverages worldwide.',
  referenceSnapshot: '2026-10-02',
  features: [
    value('instrument.sector', 'Consumer Staples', 'TEXT'),
    value('instrument.industry', 'Beverages', 'TEXT'),
    value('rollup.price_stats@v2.close', 74.1, 'CURRENCY'),
    value('feature.market_cap', 3.2e11, 'COMPACT', 'usd'),
    value('feature.pe_ratio', 24.3, 'NUMBER', 'ratio'),
    value('rollup.financials@v1.revenue_ttm', 4.7e10, 'COMPACT', 'usd'),
    value('rollup.dividends@v2.last_ex_date', '2026-09-12', 'DATE'),
    {
      name: 'rollup.earnings@v1.next_earnings_date',
      value: null,
      unknown: { code: 'NULL', detail: 'null for EQ:KO on 2026-10-02' },
      info: info('DATE'),
    },
    value('rollup.earnings@v1.last_earnings_date', '2026-08-27', 'DATE'),
  ],
};

beforeEach(() => {
  hooks.useInstrumentFacts.mockReturnValue(fakeQuery({ session, instrument: stock }));
  hooks.useInstrumentEvents.mockReturnValue(
    fakeQuery([
      {
        table: 'events/earnings',
        ts: '2026-08-27T00:00:00+00:00',
        values: { reported: true, eps_forecast: 0.8, eps_reported: 0.82, time: 'pre_market' },
      },
      {
        table: 'events/earnings',
        ts: '2099-02-10T00:00:00+00:00',
        values: { reported: false, eps_forecast: 0.9 },
      },
    ]),
  );
});

describe('OverviewPanel', () => {
  it('says what the company is, its sector and the key numbers for the session', async () => {
    const { container } = render(<OverviewPanel symbol="KO" />);
    expect(screen.getByRole('heading', { name: 'KO · overview' })).toBeInTheDocument();
    expect(screen.getByText('Coca-Cola Co')).toBeInTheDocument();
    expect(screen.getByText('Consumer Staples')).toBeInTheDocument();
    expect(screen.getByText('Beverages')).toBeInTheDocument();
    expect(screen.getByText('Makes and sells non-alcoholic beverages worldwide.')).toBeVisible();
    const strip = screen.getByRole('region', { name: 'KO headline numbers' });
    expect(strip).toHaveTextContent('P/E ratio24.30');
    expect(strip).toHaveTextContent('Revenue (TTM)$47B');
    expect(screen.getByText('Values for the session of 2 Oct 2026.')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows the next earnings date as Unknown with the reason, never one from the events', () => {
    render(<OverviewPanel symbol="KO" />);
    const strip = screen.getByRole('region', { name: 'KO headline numbers' });
    expect(strip).toHaveTextContent('Next earningsUnknown');
    expect(strip).not.toHaveTextContent('10 Feb 2099');
    const earnings = screen.getByLabelText('Earnings');
    expect(earnings).toHaveTextContent('Last earnings27 Aug 2026');
    expect(earnings).toHaveTextContent('EPS reportedforecast $0.80$0.82');
    expect(earnings).toHaveTextContent('no report date on or after the session');
  });

  it('names the nightly tables the session is missing', () => {
    hooks.useInstrumentFacts.mockReturnValue(
      fakeQuery({
        session: { ...session, missing: ['rollups/instrument/earnings@v1'] },
        instrument: stock,
      }),
    );
    render(<OverviewPanel symbol="KO" />);
    expect(screen.getByText(/Not stored for 2 Oct 2026: earnings@v1/)).toBeInTheDocument();
  });

  it('says so when there is no description, and shows no fund section for a stock', () => {
    hooks.useInstrumentFacts.mockReturnValue(
      fakeQuery({ session, instrument: { ...stock, description: null } }),
    );
    render(<OverviewPanel symbol="KO" fund={<Text>holdings</Text>} />);
    expect(screen.getByText('No description stored for KO yet.')).toBeInTheDocument();
    expect(screen.queryByText('holdings')).not.toBeInTheDocument();
  });

  it('shows the fund section for an ETF', () => {
    hooks.useInstrumentFacts.mockReturnValue(
      fakeQuery({
        session,
        instrument: { ...stock, name: 'SPDR S&P 500', securityType: 'ETF', isEtf: true },
      }),
    );
    render(<OverviewPanel symbol="SPY" fund={<Text>holdings</Text>} />);
    expect(screen.getByText('holdings')).toBeInTheDocument();
  });

  it('says when the ticker is not in the session reference snapshot', () => {
    hooks.useInstrumentFacts.mockReturnValue(fakeQuery({ session, instrument: null }));
    render(<OverviewPanel symbol="ZZZ" />);
    expect(
      screen.getByText('ZZZ is not in the reference snapshot for 2 Oct 2026.'),
    ).toBeInTheDocument();
  });

  it('shows an error with a retry when the read fails', () => {
    hooks.useInstrumentFacts.mockReturnValue(fakeQuery(undefined, { isError: true }));
    render(<OverviewPanel symbol="KO" />);
    expect(screen.getByText('KO failed to load.')).toBeInTheDocument();
  });
});
