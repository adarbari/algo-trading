import { describe, expect, it } from 'vitest';

import type { ServedValue } from '@/entities/feature';
import type { InstrumentEvent } from '@/entities/instrument';

import {
  earningsGroup,
  exchangeLabel,
  factGroups,
  headlineStats,
  missingTables,
  OVERVIEW_FEATURES,
  profileOf,
  valuesOf,
  type FactsInstrument,
} from './overview';

type Format = ServedValue['info']['format'];

const known = (name: string, value: unknown, format: Format = 'NUMBER', unit?: string) => ({
  name,
  value,
  unknown: null,
  info: { format, unit: unit ?? null, dtype: 'float', nullMeaning: 'not known' },
});

const unknown = (
  name: string,
  code: 'NO_PARTITION' | 'NO_ROW' | 'NULL',
  format: Format = 'NUMBER',
  nullMeaning = 'not known',
) => ({
  name,
  value: null,
  unknown: { code, detail: `rollups/instrument/x@v1 has no partition for 2026-10-02` },
  info: { format, unit: null, dtype: 'date', nullMeaning },
});

const NEXT = 'rollup.earnings@v1.next_earnings_date';
const LAST = 'rollup.earnings@v1.last_earnings_date';

const instrument = (
  features: ServedValue[],
  overrides: Partial<FactsInstrument> = {},
): FactsInstrument => ({
  instrumentId: 'EQ:AAPL',
  symbol: 'AAPL',
  name: 'Apple Inc.',
  securityType: 'COMMON_STOCK',
  exchange: 'NASDAQ',
  isEtf: false,
  description: null,
  referenceSnapshot: '2026-10-02',
  features: features as FactsInstrument['features'],
  ...overrides,
});

const stock = () =>
  instrument([
    known('instrument.sector', 'Technology', 'TEXT'),
    known('instrument.industry', 'Electronic Computers', 'TEXT'),
    known('instrument.in_sp500', true, 'FLAG'),
    known('instrument.optionable', true, 'FLAG'),
    known('rollup.price_stats@v2.close', 333.69, 'CURRENCY'),
    known('feature.market_cap', 4.87e12, 'COMPACT', 'usd'),
    unknown('feature.pe_ratio', 'NULL'),
    unknown('rollup.financials@v1.revenue_ttm', 'NO_PARTITION', 'COMPACT'),
    known('feature.div_yield', 0.0032, 'PERCENT'),
    known('feature.pct_from_high_52w', -0.04, 'PERCENT'),
    known(NEXT, '2026-10-29', 'DATE'),
    known('rollup.earnings@v1.days_to_earnings', 19),
    known('rollup.earnings@v1.earnings_time', 'pre', 'CATEGORY'),
    known(LAST, '2026-07-30', 'DATE'),
  ]);

const earnings = (ts: string, values: Record<string, unknown>): InstrumentEvent => ({
  table: 'events/earnings',
  kind: 'earnings',
  date: ts,
  ts: `${ts}T00:00:00+00:00`,
  values,
});

describe('profileOf', () => {
  it('names the company, its kind, sector and listing facts', () => {
    const aapl = stock();
    expect(profileOf(aapl, valuesOf(aapl))).toEqual({
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
    const tqqq = instrument(
      [
        known('instrument.is_leveraged', true, 'FLAG'),
        known('instrument.leverage', 3),
        known('instrument.tracks', 'Nasdaq-100', 'TEXT'),
        unknown('instrument.sector', 'NULL', 'TEXT'),
      ],
      {
        name: 'ProShares UltraPro QQQ',
        securityType: 'ETF',
        isEtf: true,
        description: ' Seeks 3x the daily return of the Nasdaq-100. ',
      },
    );
    const profile = profileOf(tqqq, valuesOf(tqqq));
    expect([profile.isEtf, profile.kind, profile.sector]).toEqual([true, 'ETF', null]);
    expect(profile.description).toBe('Seeks 3x the daily return of the Nasdaq-100.');
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
  it('shows stored values with the server format, a missing partition as Unknown, and leaves out what does not apply', () => {
    const stats = headlineStats(valuesOf(stock()));
    expect(stats.map((s) => [s.id, s.value])).toEqual([
      ['close', 333.69],
      ['market-cap', 4.87e12],
      ['revenue', 'Unknown'], // no partition for the session: said so
      ['next', '2026-10-29'], // P/E is null for AAPL here: left out
    ]);
    expect(stats[1]?.format).toEqual({ kind: 'currency-compact' });
    expect(stats[2]?.sub).toMatch(/^not stored for this session/);
    expect(stats[3]?.sub).toBe('in 19 sessions, before the open');
    const groups = factGroups(valuesOf(stock()));
    expect(groups.map((g) => g.id)).toEqual(['range', 'dividends']);
    expect(groups[0]?.items[0]?.format).toEqual({ kind: 'delta', unit: 'percent' });
    expect(groups[1]?.items[0]?.format).toEqual({ kind: 'percent' });
  });

  it('asks for every fact it shows in one request', () => {
    expect(OVERVIEW_FEATURES).toContain(NEXT);
    expect(OVERVIEW_FEATURES).toContain('rollup.iv30@v1.iv30');
    expect(new Set(OVERVIEW_FEATURES).size).toBe(OVERVIEW_FEATURES.length);
    expect(OVERVIEW_FEATURES.length).toBeLessThanOrEqual(60);
  });
});

describe('earningsGroup', () => {
  const events = [
    earnings('2026-07-30', {
      reported: true,
      eps_forecast: 1.4,
      eps_reported: 1.57,
      surprise_pct: 12.1,
      time: 'after_hours',
    }),
    earnings('2026-10-29', { reported: false, eps_forecast: 1.98, fiscal_quarter: 'Sep/2026' }),
    // A later report the server did not name: never shown as "next".
    earnings('2027-01-28', { reported: false, eps_forecast: 2.2 }),
  ];

  it('shows the dates the server sent, with the EPS figures stored for exactly those dates', () => {
    const group = earningsGroup(valuesOf(stock()), events);
    expect(group.items.map((i) => [i.id, i.value])).toEqual([
      ['next', '2026-10-29'],
      ['forecast', 1.98],
      ['last', '2026-07-30'],
      ['reported', 1.57],
      ['surprise', expect.closeTo(0.121) as unknown],
    ]);
    expect(group.items[1]?.hint).toBe('Quarter Sep/2026');
  });

  it('says why the next date is not known, never deriving it from the events', () => {
    const mrvl = instrument([
      unknown(NEXT, 'NULL', 'DATE', 'no report date on or after the session'),
      known(LAST, '2026-08-27', 'DATE'),
    ]);
    const group = earningsGroup(valuesOf(mrvl), events);
    expect(group.items.map((i) => [i.id, i.value, i.hint])).toEqual([
      ['next', 'Unknown', 'no report date on or after the session'],
      ['last', '2026-08-27', undefined],
    ]);
  });

  it('says the last date is unknown when the rollup has no partition', () => {
    const bare = instrument([
      unknown(NEXT, 'NO_PARTITION', 'DATE'),
      unknown(LAST, 'NO_ROW', 'DATE'),
    ]);
    const group = earningsGroup(valuesOf(bare), events);
    expect(group.items.map((i) => [i.id, i.value])).toEqual([
      ['next', 'Unknown'],
      ['last', 'Unknown'],
    ]);
    expect(group.items[1]?.hint).toBe('no row for this instrument in this session');
  });
});

describe('missingTables', () => {
  it('names the missing nightly tables briefly', () => {
    expect(missingTables(['rollups/instrument/earnings@v1', 'bars/1d'])).toEqual([
      'earnings@v1',
      'bars/1d',
    ]);
  });
});
