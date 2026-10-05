import { describe, expect, it } from 'vitest';

import type { InstrumentDetail, InstrumentEvent } from '@/entities/instrument';

import {
  earningsFacts,
  earningsGroup,
  exchangeLabel,
  factGroups,
  headlineStats,
  nextAndLast,
  nextEarningsDate,
  profileOf,
} from './overview';

const detail = (overrides: Partial<InstrumentDetail> = {}): InstrumentDetail => ({
  instrument_id: 'EQ:AAPL',
  reference_snapshot: '2026-10-02',
  reference: {
    name: 'Apple Inc. - Common Stock',
    exchange: 'NASDAQ',
    security_type: 'COMMON_STOCK',
    is_etf: false,
    in_sp500: true,
    optionable: true,
  },
  company: { name: 'Apple Inc.', sector: 'Technology', industry: 'Electronic Computers' },
  features: {
    'rollup.price_stats@v2.close': 333.69,
    'feature.market_cap': 4.87e12,
    'feature.div_yield': 0.0032,
    'rollup.earnings@v1.next_earnings_date': '2026-10-29',
    'rollup.earnings@v1.days_to_earnings': 19,
  },
  feature_sessions: {},
  ...overrides,
});

const earnings = (ts: string, values: Record<string, unknown>): InstrumentEvent => ({
  table: 'events/earnings',
  ts: `${ts}T00:00:00+00:00`,
  values,
});

describe('profileOf', () => {
  it('names the company, its kind, sector and listing facts', () => {
    expect(profileOf(detail())).toEqual({
      name: 'Apple Inc.',
      kind: 'Stock',
      isEtf: false,
      description: null,
      sector: 'Technology',
      industry: 'Electronic Computers',
      exchange: 'Nasdaq',
      website: null,
      tags: ['S&P 500', 'Optionable'],
    });
  });

  it('reads a stored description and describes a leveraged ETF', () => {
    const profile = profileOf(
      detail({
        reference: {
          name: 'ProShares UltraPro QQQ',
          security_type: 'ETF',
          is_etf: true,
          is_leveraged: true,
          leverage: 3,
          tracks: 'Nasdaq-100',
          description: ' Seeks 3x the daily return of the Nasdaq-100. ',
        },
        company: null,
      }),
    );
    expect(profile.isEtf).toBe(true);
    expect(profile.kind).toBe('ETF');
    expect(profile.description).toBe('Seeks 3x the daily return of the Nasdaq-100.');
    expect(profile.sector).toBeNull();
    expect(profile.tags).toEqual(['3x leveraged', 'Tracks Nasdaq-100']);
  });
});

describe('exchangeLabel', () => {
  it('writes the venue in words', () => {
    expect(exchangeLabel('NYSE_ARCA')).toBe('NYSE Arca');
    expect(exchangeLabel('BATS_Z')).toBe('BATS Z');
  });
});

describe('headlineStats and factGroups', () => {
  it('lists only the numbers the store has', () => {
    const stats = headlineStats(detail(), '2026-10-29');
    expect(stats.map((s) => s.id)).toEqual(['close', 'market-cap', 'next-earnings']);
    expect(factGroups(detail()).map((g) => g.id)).toEqual(['dividends']);
  });

  it('shows revenue and P/E as soon as their features are stored', () => {
    const withFundamentals = detail({
      features: {
        'feature.pe_ratio': 31.2,
        'rollup.financials@v1.revenue_ttm': 4.1e11,
        'rollup.financials@v1.eps_ttm': 10.7,
      },
    });
    expect(headlineStats(withFundamentals, null).map((s) => s.id)).toEqual(['pe', 'revenue']);
    expect(factGroups(withFundamentals)[0]?.items.map((i) => i.id)).toEqual(['eps']);
  });
});

describe('earnings', () => {
  const events = [
    earnings('2026-07-30', {
      reported: true,
      eps_forecast: 1.4,
      eps_reported: 1.57,
      surprise_pct: 12.1,
      time: 'after_hours',
    }),
    earnings('2026-10-29', {
      reported: false,
      eps_forecast: 1.98,
      fiscal_quarter: 'Sep/2026',
      time: 'pre_market',
    }),
  ];

  it('orders the facts by date and finds the next and the last report', () => {
    const facts = earningsFacts([...events].reverse());
    expect(facts.map((f) => f.date)).toEqual(['2026-07-30', '2026-10-29']);
    const { next, last } = nextAndLast(facts, '2026-10-04');
    expect(next?.date).toBe('2026-10-29');
    expect(last?.epsReported).toBe(1.57);
    expect(last?.surprise).toBeCloseTo(0.121);
  });

  it('builds the earnings facts with the forecast, reported EPS and surprise', () => {
    const group = earningsGroup(detail(), events, '2026-10-04');
    expect(group?.items.map((i) => [i.id, i.value])).toEqual([
      ['next', '2026-10-29'],
      ['forecast', 1.98],
      ['last', '2026-07-30'],
      ['reported', 1.57],
      ['surprise', expect.closeTo(0.121) as unknown],
    ]);
    expect(group?.items[0]?.hint).toBe('in 19 sessions, Before the open');
  });

  it('falls back to the events when the rollup has no dates, and to nothing', () => {
    const bare = detail({ features: {} });
    expect(nextEarningsDate(bare, events, '2026-10-04')).toBe('2026-10-29');
    expect(earningsGroup(bare, [], '2026-10-04')).toBeNull();
  });
});
