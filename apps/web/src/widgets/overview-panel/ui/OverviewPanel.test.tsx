import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { OverviewPanel } from './OverviewPanel';

const hooks = vi.hoisted(() => ({
  useInstrumentFacts: vi.fn(),
  useInstrumentEvents: vi.fn(),
  useRegimeEpisodes: vi.fn(),
}));

vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrumentFacts: hooks.useInstrumentFacts,
  useInstrumentEvents: hooks.useInstrumentEvents,
}));

vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRegimeEpisodes: hooks.useRegimeEpisodes,
}));

const episode = (key: string, name: string) => ({ key, name });
const EPISODES = [
  episode('covid_2020', 'Covid crash, early 2020'),
  episode('hikes_2022', 'Rate-hike bear market, 2022'),
  episode('tariffs_2025', 'Tariff shock, spring 2025'),
];

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
  unavailable: [],
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
    value('rollup.financials@v2.revenue_ttm', 4.7e10, 'COMPACT', 'usd'),
    value('rollup.dividends@v2.last_ex_date', '2026-09-12', 'DATE'),
    {
      name: 'rollup.earnings@v1.next_earnings_date',
      value: null,
      unknown: {
        code: 'NULL',
        kind: 'NOT_STORED',
        guideTerm: 'unavailable_not_stored',
        cause: null,
      },
      info: info('DATE'),
    },
    value('rollup.earnings@v1.last_earnings_date', '2026-08-27', 'DATE'),
    value('rollup.episode_behaviour@v1.beta_252d', 0.62, 'NUMBER', 'ratio'),
    value('rollup.episode_behaviour@v1.dd_tariffs_2025', -0.08, 'PERCENT', 'decimal'),
    value('rollup.episode_behaviour@v1.recovery_sessions_tariffs_2025', 12, 'NUMBER', 'sessions'),
    value('rollup.episode_behaviour@v1.dd_hikes_2022', -0.21, 'PERCENT', 'decimal'),
    {
      name: 'rollup.episode_behaviour@v1.dd_covid_2020',
      value: null,
      unknown: {
        code: 'NO_PARTITION',
        kind: 'SYSTEM',
        guideTerm: 'unavailable_system',
        cause: null,
      },
      info: info('PERCENT', 'decimal'),
    },
  ],
};

beforeEach(() => {
  hooks.useRegimeEpisodes.mockReturnValue(fakeQuery({ episodes: EPISODES, recessions: [] }));
  hooks.useInstrumentFacts.mockReturnValue(fakeQuery({ session, instrument: stock }));
  hooks.useInstrumentEvents.mockReturnValue(
    fakeQuery([
      {
        table: 'events/earnings',
        kind: 'earnings',
        date: '2026-08-27',
        ts: '2026-08-27T00:00:00+00:00',
        values: { reported: true, eps_forecast: 0.8, eps_reported: 0.82, time: 'pre_market' },
      },
      {
        table: 'events/earnings',
        kind: 'earnings',
        date: '2099-02-10',
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

  it('shows beta and the drawdown in each rough episode, in plain names, newest first', () => {
    render(<OverviewPanel symbol="KO" />);
    const rough = screen.getByLabelText('In rough markets');
    expect(rough).toHaveTextContent('Beta to SPY (1 year)0.62');
    expect(rough).toHaveTextContent(
      'Tariff shock, spring 2025Back at its pre-episode high 12 sessions after the low−8.00%',
    );
    expect(rough).toHaveTextContent('Rate-hike bear market, 2022−21.00%');
    expect(hooks.useInstrumentFacts).toHaveBeenCalledWith(
      'KO',
      expect.arrayContaining(['rollup.episode_behaviour@v1.beta_252d']),
    );
  });

  it('waits for the episode names, and spaces the key of an episode the API does not name', () => {
    hooks.useRegimeEpisodes.mockReturnValue(fakeQuery(undefined, { isPending: true }));
    const { unmount } = render(<OverviewPanel symbol="KO" />);
    expect(screen.queryByText('In rough markets')).not.toBeInTheDocument();
    unmount();
    hooks.useRegimeEpisodes.mockReturnValue(fakeQuery({ episodes: [], recessions: [] }));
    render(<OverviewPanel symbol="KO" />);
    expect(screen.getByLabelText('In rough markets')).toHaveTextContent('tariffs 2025');
  });

  it('reads Unknown with the reason for an episode the session has no partition for', () => {
    render(<OverviewPanel symbol="KO" />);
    const rough = screen.getByLabelText('In rough markets');
    expect(rough).toHaveTextContent(
      'Covid crash, early 2020not available because of a system error',
    );
    expect(rough).toHaveTextContent('Unknown');
  });

  it('leaves the line out for a name with no episode values', () => {
    hooks.useInstrumentFacts.mockReturnValue(
      fakeQuery({
        session,
        instrument: {
          ...stock,
          features: stock.features.filter((f) => !f.name.includes('episode_behaviour')),
        },
      }),
    );
    render(<OverviewPanel symbol="KO" />);
    expect(screen.queryByText('In rough markets')).not.toBeInTheDocument();
  });

  it('tells what the session is missing, by kind', () => {
    hooks.useInstrumentFacts.mockReturnValue(
      fakeQuery({
        session: {
          ...session,
          unavailable: [
            {
              kind: 'SYSTEM',
              features: ['rollup.earnings@v1.next_earnings_date'],
              guideTerm: 'unavailable_system',
              cause: null,
            },
          ],
        },
        instrument: stock,
      }),
    );
    render(<OverviewPanel symbol="KO" />);
    expect(screen.getByText('Not available: system error')).toBeInTheDocument();
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
