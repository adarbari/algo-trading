/**
 * What the Overview shows for one instrument, as plain rows, from the instrument's facts for
 * the session (GraphQL `InstrumentFacts`: typed identity + catalogue features by name): who it
 * is (name, kind, sector, description), the headline numbers, the grouped key facts (size and
 * valuation, price range, dividends, options) and the earnings dates.
 *
 * Every value is the server's for `session.date`, formatted with the server's `info.format`.
 * A fact the session has no partition for reads "Unknown" with the reason; a fact that does
 * not apply to the instrument (no row, null) is left out, except the earnings dates, which
 * always say what is known. The next / last earnings dates are catalogue features
 * (`rollup.earnings@v1`); the events only add the EPS figures of the date the server names.
 */
import { formatValue, type KeyValueItem, type StatItem, type ValueFormat } from '@algotrade/ui';

import {
  isUnknown,
  shownValue,
  unknownLabel,
  unknownReason,
  valueFormat,
  type ServedValue,
} from '@/entities/feature';
import { earningsOn, reportTime, type InstrumentEvent } from '@/entities/instrument';
import { typeLabel } from '@/features/ticker-filter';
import { feature, type gqlTypes, type SiteFeature } from '@/shared/api';

export type FactsData = gqlTypes.InstrumentFactsQuery;
export type FactsInstrument = NonNullable<FactsData['instrument']>;

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

export interface FactSpec {
  id: string;
  label: string;
  name: SiteFeature;
  /** A change: shown signed, with an up / down tone. */
  signed?: boolean;
}

const PROFILE = {
  sector: feature('instrument.sector'),
  industry: feature('instrument.industry'),
  website: feature('instrument.website'),
  sp500: feature('instrument.in_sp500'),
  optionable: feature('instrument.optionable'),
  leverage: feature('instrument.leverage'),
  inverse: feature('instrument.is_inverse'),
  leveraged: feature('instrument.is_leveraged'),
  tracks: feature('instrument.tracks'),
} as const;

const EARNINGS = {
  next: feature('rollup.earnings@v1.next_earnings_date'),
  last: feature('rollup.earnings@v1.last_earnings_date'),
  days: feature('rollup.earnings@v1.days_to_earnings'),
  time: feature('rollup.earnings@v1.earnings_time'),
} as const;

/** Headline numbers. */
const HEADLINE: readonly FactSpec[] = [
  { id: 'close', label: 'Last close', name: feature('rollup.price_stats@v2.close') },
  { id: 'market-cap', label: 'Market cap', name: feature('feature.market_cap') },
  { id: 'pe', label: 'P/E ratio', name: feature('feature.pe_ratio') },
  { id: 'revenue', label: 'Revenue (TTM)', name: feature('rollup.financials@v2.revenue_ttm') },
];

const GROUPS: readonly { id: string; title: string; facts: readonly FactSpec[] }[] = [
  {
    id: 'size',
    title: 'Size and valuation',
    facts: [
      {
        id: 'shares',
        label: 'Shares outstanding',
        name: feature('rollup.fundamentals@v3.shares_outstanding'),
      },
      {
        id: 'growth',
        label: 'Revenue growth (YoY)',
        name: feature('feature.revenue_growth_yoy'),
        signed: true,
      },
      {
        id: 'income',
        label: 'Net income (TTM)',
        name: feature('rollup.financials@v2.net_income_ttm'),
      },
      {
        id: 'eps',
        label: 'Diluted EPS (TTM)',
        name: feature('rollup.financials@v2.eps_diluted_ttm'),
      },
      {
        id: 'adv',
        label: 'Average daily volume ($, 20d)',
        name: feature('rollup.price_stats@v2.adv_usd_20d'),
      },
    ],
  },
  {
    id: 'range',
    title: 'Price',
    facts: [
      { id: 'high', label: '52-week high', name: feature('rollup.price_stats@v2.high_52w') },
      { id: 'low', label: '52-week low', name: feature('rollup.price_stats@v2.low_52w') },
      {
        id: 'from-high',
        label: 'From 52-week high',
        name: feature('feature.pct_from_high_52w'),
        signed: true,
      },
      {
        id: 'hv30',
        label: 'Realised volatility (30d)',
        name: feature('rollup.price_stats@v2.hv30'),
      },
    ],
  },
  {
    id: 'dividends',
    title: 'Dividends',
    facts: [
      { id: 'yield', label: 'Yield', name: feature('feature.div_yield') },
      { id: 'ttm', label: 'Paid, last 12 months', name: feature('rollup.dividends@v2.div_ttm') },
      {
        id: 'ex',
        label: 'Last ex-dividend date',
        name: feature('rollup.dividends@v2.last_ex_date'),
      },
    ],
  },
  {
    id: 'options',
    title: 'Options',
    facts: [
      { id: 'iv30', label: 'Implied volatility (30d)', name: feature('rollup.iv30@v1.iv30') },
      { id: 'ivr', label: 'IV rank', name: feature('feature.iv_rank') },
      { id: 'ivhv', label: 'IV / HV', name: feature('feature.iv_hv_ratio') },
    ],
  },
];

/** Every catalogue feature the Overview asks for (one request). */
export const OVERVIEW_FEATURES: readonly SiteFeature[] = [
  ...Object.values(PROFILE),
  ...Object.values(EARNINGS),
  ...HEADLINE.map((f) => f.name),
  ...GROUPS.flatMap((g) => g.facts.map((f) => f.name)),
];

/** The served values by catalogue name. */
export type Values = ReadonlyMap<string, ServedValue>;

export function valuesOf(instrument: FactsInstrument): Values {
  return new Map(instrument.features.map((v) => [v.name, v]));
}

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() ? value.trim() : null;
const num = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;
const known = (values: Values, name: string): unknown => values.get(name)?.value ?? null;

const EXCHANGES: Readonly<Record<string, string>> = {
  NYSE_ARCA: 'NYSE Arca',
  NYSE_AMERICAN: 'NYSE American',
  NASDAQ: 'Nasdaq',
};

/** `NYSE_ARCA` -> `NYSE Arca`; an unknown venue keeps its code with spaces for underscores. */
export function exchangeLabel(code: string): string {
  return EXCHANGES[code] ?? code.replace(/_/g, ' ');
}

export function profileOf(instrument: FactsInstrument, values: Values): Profile {
  const tags: string[] = [];
  if (known(values, PROFILE.sp500) === true) tags.push('S&P 500');
  if (known(values, PROFILE.optionable) === true) tags.push('Optionable');
  const leverage = num(known(values, PROFILE.leverage));
  if (known(values, PROFILE.inverse) === true) {
    tags.push(leverage ? `${Math.abs(leverage)}x inverse` : 'Inverse');
  } else if (known(values, PROFILE.leveraged) === true) {
    tags.push(leverage ? `${leverage}x leveraged` : 'Leveraged');
  }
  const tracks = text(known(values, PROFILE.tracks));
  if (tracks) tags.push(`Tracks ${tracks}`);
  const securityType = text(instrument.securityType);
  return {
    name: instrument.name,
    kind: securityType ? typeLabel(securityType) : instrument.isEtf ? 'ETF' : 'Instrument',
    isEtf: instrument.isEtf,
    description: text(instrument.description),
    sector: text(known(values, PROFILE.sector)),
    industry: text(known(values, PROFILE.industry)),
    exchange: exchangeLabel(text(instrument.exchange) ?? '') || null,
    website: text(known(values, PROFILE.website)),
    tags,
  };
}

const UNKNOWN = 'Unknown';

/** A row with its stable id (a headline stat uses the same id). */
export type Fact = KeyValueItem & { id: string };

function formatOf(spec: FactSpec, value: ServedValue): ValueFormat {
  const format = valueFormat(value.info);
  return spec.signed && format.kind === 'percent' ? { kind: 'delta', unit: 'percent' } : format;
}

/** A fact's row: its value, "Unknown" with the reason when the session has no partition for
 * it, nothing when it does not apply to the instrument. */
export function factItem(values: Values, spec: FactSpec): Fact | null {
  const value = values.get(spec.name);
  if (!value) return null;
  if (isUnknown(value)) {
    if (value.unknown?.code !== 'NO_PARTITION') return null;
    return { id: spec.id, label: spec.label, value: UNKNOWN, hint: unknownReason(value) };
  }
  return {
    id: spec.id,
    label: spec.label,
    value: shownValue(value.value) as string | number,
    format: formatOf(spec, value),
  };
}

const sessionsText = (days: unknown): string | null => {
  const n = num(days);
  if (n === null) return null;
  return n === 0 ? 'today' : `in ${n} session${n === 1 ? '' : 's'}`;
};

const asStat = (item: Fact): StatItem => ({
  id: item.id,
  label: item.label,
  value: item.value,
  ...(item.format ? { format: item.format } : {}),
  ...(item.hint ? { sub: item.hint } : {}),
});

/** The next report date as the session knows it: the date, or Unknown with the reason. */
function nextEarnings(values: Values): Fact {
  const next = values.get(EARNINGS.next);
  if (!next || isUnknown(next)) {
    return {
      id: 'next',
      label: 'Next earnings',
      value: unknownLabel(next?.unknown?.code, next?.unknown?.reason),
      hint: unknownReason(next),
    };
  }
  const when = [
    sessionsText(known(values, EARNINGS.days)),
    reportTime(known(values, EARNINGS.time)),
  ]
    .filter(Boolean)
    .join(', ');
  return {
    id: 'next',
    label: 'Next earnings',
    value: String(next.value),
    format: { kind: 'date' },
    ...(when ? { hint: when } : {}),
  };
}

/** The headline numbers, then the next report date (or why it is not known). */
export function headlineStats(values: Values): StatItem[] {
  const stats = HEADLINE.flatMap((spec) => {
    const item = factItem(values, spec);
    return item ? [asStat(item)] : [];
  });
  return [...stats, asStat(nextEarnings(values))];
}

/** Next and last report dates (each known, or Unknown with the reason), with the EPS figures
 * the events store for exactly those dates. */
export function earningsGroup(values: Values, events: readonly InstrumentEvent[]): FactGroup {
  const items: KeyValueItem[] = [nextEarnings(values)];
  const nextDate = text(known(values, EARNINGS.next));
  const upcoming = earningsOn(events, nextDate);
  if (upcoming?.epsForecast != null) {
    items.push({
      id: 'forecast',
      label: 'EPS forecast',
      value: upcoming.epsForecast,
      format: { kind: 'currency' },
      ...(upcoming.quarter ? { hint: `Quarter ${upcoming.quarter}` } : {}),
    });
  }
  const last = values.get(EARNINGS.last);
  const lastDate = text(known(values, EARNINGS.last));
  if (!lastDate) {
    items.push({
      id: 'last',
      label: 'Last earnings',
      value: unknownLabel(last?.unknown?.code, last?.unknown?.reason),
      hint: unknownReason(last),
    });
    return { id: 'earnings', title: 'Earnings', items };
  }
  items.push({ id: 'last', label: 'Last earnings', value: lastDate, format: { kind: 'date' } });
  const report = earningsOn(events, lastDate);
  if (report?.epsReported != null) {
    items.push({
      id: 'reported',
      label: 'EPS reported',
      value: report.epsReported,
      format: { kind: 'currency' },
      ...(report.epsForecast != null
        ? { hint: `forecast ${formatValue(report.epsForecast, { kind: 'currency' }).text}` }
        : {}),
    });
  }
  if (report?.surprise != null) {
    items.push({
      id: 'surprise',
      label: 'EPS surprise',
      value: report.surprise,
      format: { kind: 'delta' },
    });
  }
  return { id: 'earnings', title: 'Earnings', items };
}

export function factGroups(values: Values): FactGroup[] {
  return GROUPS.map((group) => ({
    id: group.id,
    title: group.title,
    items: group.facts.flatMap((spec) => factItem(values, spec) ?? []),
  })).filter((group) => group.items.length > 0);
}

/** The expected nightly tables with no partition for the session, by short name. */
export function missingTables(missing: readonly string[]): string[] {
  return missing.map((table) => table.replace(/^rollups\/instrument\//, ''));
}
