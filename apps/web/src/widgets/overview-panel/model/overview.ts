/**
 * What the Overview shows for one instrument, as plain rows: who it is (name, kind, sector,
 * description), the headline numbers, and the grouped key facts (size and valuation, price
 * range, dividends, options, earnings). A fact is listed only when the store has a value for
 * it, so a new stored feature (revenue, P/E) appears here once its field is in the detail.
 */
import type { KeyValueItem, StatItem, ValueFormat } from '@algotrade/ui';

import {
  displayName,
  fieldValue,
  type InstrumentDetail,
  type InstrumentEvent,
} from '@/entities/instrument';
import { typeLabel } from '@/features/ticker-filter';

export interface Profile {
  name: string;
  /** "Stock", "ETF", ... */
  kind: string;
  isEtf: boolean;
  /** The description as stored (null: none stored yet). */
  description: string | null;
  sector: string | null;
  industry: string | null;
  exchange: string | null;
  website: string | null;
  /** Short facts about the listing: "S&P 500", "Optionable", "3x leveraged", "Tracks ...". */
  tags: string[];
}

export interface FactGroup {
  id: string;
  title: string;
  items: KeyValueItem[];
}

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() ? value.trim() : null;
const num = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

/** Field `name` of the detail when it holds a value, else null. */
const present = (detail: InstrumentDetail, name: string): unknown => {
  const value = fieldValue(detail, name);
  return value === undefined || value === null || value === '' ? null : value;
};

const EXCHANGES: Readonly<Record<string, string>> = {
  NYSE_ARCA: 'NYSE Arca',
  NYSE_AMERICAN: 'NYSE American',
  NASDAQ: 'Nasdaq',
};

/** `NYSE_ARCA` -> `NYSE Arca`; an unknown venue keeps its code with spaces for underscores. */
export function exchangeLabel(code: string): string {
  return EXCHANGES[code] ?? code.replace(/_/g, ' ');
}

export function profileOf(detail: InstrumentDetail): Profile {
  const securityType = text(fieldValue(detail, 'instrument.security_type'));
  const isEtf = fieldValue(detail, 'instrument.is_etf') === true || securityType === 'ETF';
  const tags: string[] = [];
  if (fieldValue(detail, 'instrument.in_sp500') === true) tags.push('S&P 500');
  if (fieldValue(detail, 'instrument.optionable') === true) tags.push('Optionable');
  const leverage = num(fieldValue(detail, 'instrument.leverage'));
  if (fieldValue(detail, 'instrument.is_inverse') === true) {
    tags.push(leverage ? `${Math.abs(leverage)}x inverse` : 'Inverse');
  } else if (fieldValue(detail, 'instrument.is_leveraged') === true) {
    tags.push(leverage ? `${leverage}x leveraged` : 'Leveraged');
  }
  const tracks = text(fieldValue(detail, 'instrument.tracks'));
  if (tracks) tags.push(`Tracks ${tracks}`);
  return {
    name: displayName(detail),
    kind: securityType ? typeLabel(securityType) : isEtf ? 'ETF' : 'Instrument',
    isEtf,
    description: text(fieldValue(detail, 'instrument.description')),
    sector: text(fieldValue(detail, 'instrument.sector')),
    industry: text(fieldValue(detail, 'instrument.industry')),
    exchange: exchangeLabel(text(fieldValue(detail, 'instrument.exchange')) ?? '') || null,
    website: text(fieldValue(detail, 'instrument.website')),
    tags,
  };
}

interface FactSpec {
  id: string;
  label: string;
  field: string;
  format: ValueFormat;
  hint?: string;
}

const PRICE = 'rollup.price_stats@v2.';
const EARNINGS = 'rollup.earnings@v1.';

/** Headline numbers; each shows only when stored. Revenue and P/E join once ingested. */
const HEADLINE: readonly FactSpec[] = [
  { id: 'close', label: 'Last close', field: `${PRICE}close`, format: { kind: 'currency' } },
  {
    id: 'market-cap',
    label: 'Market cap',
    field: 'feature.market_cap',
    format: { kind: 'currency-compact' },
  },
  {
    id: 'pe',
    label: 'P/E ratio',
    field: 'feature.pe_ratio',
    format: { kind: 'number', digits: 1 },
  },
  {
    id: 'revenue',
    label: 'Revenue (TTM)',
    field: 'rollup.financials@v1.revenue_ttm',
    format: { kind: 'currency-compact' },
  },
];

const GROUPS: readonly { id: string; title: string; facts: readonly FactSpec[] }[] = [
  {
    id: 'size',
    title: 'Size and valuation',
    facts: [
      {
        id: 'shares',
        label: 'Shares outstanding',
        field: 'rollup.fundamentals@v2.shares_outstanding',
        format: { kind: 'compact' },
      },
      {
        id: 'growth',
        label: 'Revenue growth (YoY)',
        field: 'feature.revenue_growth_yoy',
        format: { kind: 'delta' },
      },
      {
        id: 'income',
        label: 'Net income (TTM)',
        field: 'rollup.financials@v1.net_income_ttm',
        format: { kind: 'currency-compact' },
      },
      {
        id: 'eps',
        label: 'Diluted EPS (TTM)',
        field: 'rollup.financials@v1.eps_diluted_ttm',
        format: { kind: 'currency' },
      },
      {
        id: 'adv',
        label: 'Average daily volume ($, 20d)',
        field: `${PRICE}adv_usd_20d`,
        format: { kind: 'currency-compact' },
      },
    ],
  },
  {
    id: 'range',
    title: 'Price',
    facts: [
      {
        id: 'high',
        label: '52-week high',
        field: `${PRICE}high_52w`,
        format: { kind: 'currency' },
      },
      { id: 'low', label: '52-week low', field: `${PRICE}low_52w`, format: { kind: 'currency' } },
      {
        id: 'from-high',
        label: 'From 52-week high',
        field: 'feature.pct_from_high_52w',
        format: { kind: 'delta' },
      },
      {
        id: 'hv30',
        label: 'Realised volatility (30d)',
        field: `${PRICE}hv30`,
        format: { kind: 'percent', digits: 1 },
      },
    ],
  },
  {
    id: 'dividends',
    title: 'Dividends',
    facts: [
      {
        id: 'yield',
        label: 'Yield',
        field: 'feature.div_yield',
        format: { kind: 'percent', digits: 2 },
      },
      {
        id: 'ttm',
        label: 'Paid, last 12 months',
        field: 'rollup.dividends@v2.div_ttm',
        format: { kind: 'currency' },
      },
      {
        id: 'ex',
        label: 'Last ex-dividend date',
        field: 'rollup.dividends@v2.last_ex_date',
        format: { kind: 'date' },
      },
    ],
  },
  {
    id: 'options',
    title: 'Options',
    facts: [
      {
        id: 'iv30',
        label: 'Implied volatility (30d)',
        field: 'rollup.iv30@v1.iv30',
        format: { kind: 'percent', digits: 1 },
      },
      {
        id: 'ivr',
        label: 'IV rank',
        field: 'feature.iv_rank',
        format: { kind: 'percent', digits: 0 },
      },
      {
        id: 'ivhv',
        label: 'IV / HV',
        field: 'feature.iv_hv_ratio',
        format: { kind: 'number', digits: 2 },
      },
    ],
  },
];

const toItem = (detail: InstrumentDetail, spec: FactSpec): KeyValueItem | null => {
  const value = present(detail, spec.field);
  if (value === null) return null;
  const item: KeyValueItem = {
    id: spec.id,
    label: spec.label,
    value: value as string | number,
    format: spec.format,
  };
  if (spec.hint) item.hint = spec.hint;
  return item;
};

/** The headline numbers, then the next report date when one is known. */
export function headlineStats(detail: InstrumentDetail, nextEarnings: string | null): StatItem[] {
  const stats: StatItem[] = HEADLINE.flatMap((spec) => {
    const item = toItem(detail, spec);
    return item ? [{ id: spec.id, label: spec.label, value: item.value, format: spec.format }] : [];
  });
  if (nextEarnings) {
    stats.push({
      id: 'next-earnings',
      label: 'Next earnings',
      value: nextEarnings,
      format: { kind: 'date' },
    });
  }
  return stats;
}

/** An earnings event's values for one report date. */
export interface EarningsFact {
  date: string;
  /** "Before the open", "After the close", or null when the source does not say. */
  time: string | null;
  quarter: string | null;
  epsForecast: number | null;
  epsReported: number | null;
  /** Surprise as a fraction (+0.05 is 5% above the forecast). */
  surprise: number | null;
  reported: boolean;
}

const TIMES: Readonly<Record<string, string>> = {
  pre: 'Before the open',
  pre_market: 'Before the open',
  post: 'After the close',
  after_hours: 'After the close',
};

export function earningsFacts(events: readonly InstrumentEvent[]): EarningsFact[] {
  return events
    .filter((e) => e.table === 'events/earnings')
    .map((e) => {
      const v = e.values;
      const surprise = num(v['surprise_pct']);
      return {
        date: e.ts.slice(0, 10),
        time: TIMES[text(v['time']) ?? ''] ?? null,
        quarter: text(v['fiscal_quarter']),
        epsForecast: num(v['eps_forecast']),
        epsReported: num(v['eps_reported']),
        surprise: surprise === null ? null : surprise / 100,
        reported: v['reported'] === true,
      };
    })
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** The next report on or after `today` and the latest one before it (or already reported). */
export function nextAndLast(
  facts: readonly EarningsFact[],
  today: string,
): { next: EarningsFact | null; last: EarningsFact | null } {
  const next = facts.find((f) => f.date >= today && !f.reported) ?? null;
  const past = facts.filter((f) => f.date < today || f.reported);
  return { next, last: past.at(-1) ?? null };
}

const sessionsText = (days: unknown): string | undefined => {
  const n = num(days);
  if (n === null) return undefined;
  return n === 0 ? 'today' : `in ${n} session${n === 1 ? '' : 's'}`;
};

/** The next report date: the stored rollup's, else the earliest unreported event on or after today. */
export function nextEarningsDate(
  detail: InstrumentDetail,
  events: readonly InstrumentEvent[],
  today: string,
): string | null {
  const stored = text(present(detail, `${EARNINGS}next_earnings_date`));
  return stored ?? nextAndLast(earningsFacts(events), today).next?.date ?? null;
}

export function earningsGroup(
  detail: InstrumentDetail,
  events: readonly InstrumentEvent[],
  today: string,
): FactGroup | null {
  const { next, last } = nextAndLast(earningsFacts(events), today);
  const nextDate = nextEarningsDate(detail, events, today);
  const lastDate = text(present(detail, `${EARNINGS}last_earnings_date`)) ?? last?.date ?? null;
  const items: KeyValueItem[] = [];
  if (nextDate) {
    const when = [sessionsText(present(detail, `${EARNINGS}days_to_earnings`)), next?.time]
      .filter(Boolean)
      .join(', ');
    items.push({
      id: 'next',
      label: 'Next earnings',
      value: nextDate,
      format: { kind: 'date' },
      ...(when ? { hint: when } : {}),
    });
    if (next?.epsForecast != null) {
      items.push({
        id: 'forecast',
        label: 'EPS forecast',
        value: next.epsForecast,
        format: { kind: 'currency' },
        ...(next.quarter ? { hint: `Quarter ${next.quarter}` } : {}),
      });
    }
  }
  if (lastDate) {
    items.push({ id: 'last', label: 'Last earnings', value: lastDate, format: { kind: 'date' } });
    if (last?.epsReported != null) {
      items.push({
        id: 'reported',
        label: 'EPS reported',
        value: last.epsReported,
        format: { kind: 'currency' },
        ...(last.epsForecast != null ? { hint: `forecast ${last.epsForecast.toFixed(2)}` } : {}),
      });
    }
    if (last?.surprise != null) {
      items.push({
        id: 'surprise',
        label: 'EPS surprise',
        value: last.surprise,
        format: { kind: 'delta' },
      });
    }
  }
  return items.length > 0 ? { id: 'earnings', title: 'Earnings', items } : null;
}

export function factGroups(detail: InstrumentDetail): FactGroup[] {
  return GROUPS.map((group) => ({
    id: group.id,
    title: group.title,
    items: group.facts.flatMap((spec) => toItem(detail, spec) ?? []),
  })).filter((group) => group.items.length > 0);
}
