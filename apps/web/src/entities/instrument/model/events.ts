/**
 * Instrument events (rows of every `events/*` table) as one timeline and as chart markers:
 * each kind (earnings, dividend, split, ticker / reference change) with a plain-English detail;
 * and the report stored for one earnings date (`earningsOn`: the EPS figures of the date the
 * server names as next or last; the dates themselves are catalogue features, never derived
 * here from the events).
 */
import { formatValue, type ChartEvent } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

/** A stored event as `InstrumentEvents` selects it: `kind` names its table (`events/<kind>`),
 * `date` the event date the server read it by. */
export type InstrumentEvent = NonNullable<
  gqlTypes.InstrumentEventsQuery['instrument']
>['events'][number];

export type EventKind = 'earnings' | 'dividend' | 'split' | 'change' | 'other';

export interface TimelineEvent {
  id: string;
  /** ISO day of the event. */
  date: string;
  kind: EventKind;
  /** The kind in words ("Earnings", "Ex-dividend", ...). */
  label: string;
  detail: string;
}

const KINDS: Readonly<Record<string, EventKind>> = {
  earnings: 'earnings',
  dividend: 'dividend',
  split: 'split',
  reference_change: 'change',
};

const LABELS: Readonly<Record<EventKind, string>> = {
  earnings: 'Earnings',
  dividend: 'Ex-dividend',
  split: 'Split',
  change: 'Reference change',
  other: 'Event',
};

const num = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;
const str = (value: unknown): string => (typeof value === 'string' ? value : '');
const money = (value: unknown): string => formatValue(num(value), { kind: 'currency' }).text;
const day = (value: unknown): string => formatValue(value, { kind: 'date' }).text;

/** An event's stored columns (the server sends them as a JSON object). */
function valuesOf(event: InstrumentEvent): Readonly<Record<string, unknown>> {
  const v = event.values;
  return typeof v === 'object' && v !== null ? (v as Record<string, unknown>) : {};
}

/**
 * When a report is released, in words: events store `pre_market` / `after_hours`, the
 * `earnings@v1` rollup `pre` / `post`; anything else (`unknown`, empty) says nothing.
 */
const REPORT_TIMES: Readonly<Record<string, string>> = {
  pre: 'before the open',
  pre_market: 'before the open',
  post: 'after the close',
  after_hours: 'after the close',
};

export function reportTime(value: unknown): string | null {
  return REPORT_TIMES[str(value)] ?? null;
}

function earningsDetail(v: Readonly<Record<string, unknown>>): string {
  const parts = [str(v['fiscal_quarter']) ? `Quarter ${str(v['fiscal_quarter'])}` : ''];
  const time = reportTime(v['time']);
  if (time) parts.push(time);
  if (num(v['eps_forecast']) !== null) parts.push(`EPS forecast ${money(v['eps_forecast'])}`);
  if (v['reported'] === true && num(v['eps_reported']) !== null) {
    parts.push(`reported ${money(v['eps_reported'])}`);
    const surprise = num(v['surprise_pct']);
    if (surprise !== null) {
      parts.push(`surprise ${formatValue(surprise / 100, { kind: 'delta' }).text}`);
    }
  } else if (v['reported'] === false) {
    parts.push('not reported yet');
  }
  return parts.filter(Boolean).join(' · ');
}

function dividendDetail(v: Readonly<Record<string, unknown>>): string {
  const parts = [`${money(v['cash_amount'])} cash`];
  if (str(v['pay_date'])) parts.push(`paid ${day(v['pay_date'])}`);
  if (str(v['distribution_type']) && v['distribution_type'] !== 'recurring') {
    parts.push(str(v['distribution_type']));
  }
  return parts.join(' · ');
}

/** `split_from` 1, `split_to` 4 -> "4-for-1"; a reverse split reads "1-for-80". */
export function splitRatio(v: Readonly<Record<string, unknown>>): string {
  const from = num(v['split_from']);
  const to = num(v['split_to']);
  if (from === null || to === null) return '';
  const n = (x: number) => formatValue(x, { kind: 'number', digits: Number.isInteger(x) ? 0 : 2 });
  return `${n(to).text}-for-${n(from).text}`;
}

function changeDetail(v: Readonly<Record<string, unknown>>): string {
  const change = str(v['change']);
  const from = str(v['old']);
  const to = str(v['new']);
  if (change === 'added') return `Listed: ${to}`;
  if (change === 'removed') return 'Removed from the universe';
  if (change === 'symbol' || change === 'ticker_changed') return `Ticker ${from} → ${to}`;
  if (change === 'id_changed') return `Instrument id ${from} → ${to}`;
  const what = change.replace(/_/g, ' ');
  return from || to ? `${what}: ${from || '—'} → ${to || '—'}` : what;
}

function detailOf(kind: EventKind, v: Readonly<Record<string, unknown>>): string {
  switch (kind) {
    case 'earnings':
      return earningsDetail(v);
    case 'dividend':
      return dividendDetail(v);
    case 'split': {
      const ratio = splitRatio(v);
      return v['adjustment_type'] === 'reverse_split' ? `${ratio} reverse split` : ratio;
    }
    case 'change':
      return changeDetail(v);
    default:
      return '';
  }
}

/** Every event, newest first. */
export function toTimeline(events: readonly InstrumentEvent[]): TimelineEvent[] {
  return events
    .map((event, i) => {
      const kind = KINDS[event.kind] ?? 'other';
      return {
        id: `${event.table}-${event.ts}-${i}`,
        date: event.date,
        kind,
        label: kind === 'other' ? event.kind.replace(/_/g, ' ') : LABELS[kind],
        detail: detailOf(kind, valuesOf(event)),
      };
    })
    .sort((a, b) => (a.date === b.date ? a.id.localeCompare(b.id) : b.date.localeCompare(a.date)));
}

/**
 * Dividend, split and earnings markers for the price chart, oldest first: one per kind a day
 * (a report stored by two sources, the calendar's at midnight and the 8-K's at its acceptance
 * time, is two rows of one date but one marker).
 */
export function toChartEvents(events: readonly InstrumentEvent[]): ChartEvent[] {
  const seen = new Set<string>();
  return toTimeline(events)
    .filter((e) => {
      const key = `${e.kind}|${e.date}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .flatMap((e): ChartEvent[] => {
      if (e.kind === 'dividend') {
        const cash = e.detail.split(' cash')[0] ?? '';
        return [{ time: e.date, kind: 'dividend', detail: cash }];
      }
      if (e.kind === 'split') return [{ time: e.date, kind: 'split', detail: e.detail }];
      if (e.kind === 'earnings') return [{ time: e.date, kind: 'earnings' }];
      return [];
    })
    .reverse();
}

/** The figures of one earnings report (an `events/earnings` row). */
export interface EarningsReport {
  quarter: string | null;
  epsForecast: number | null;
  epsReported: number | null;
  /** Surprise as a fraction (+0.05 is 5% above the forecast). */
  surprise: number | null;
  reported: boolean;
}

/**
 * The stored report for the earnings date `date` (ISO day, as the server sent it), else null.
 * It picks the event of a date the server named; it never decides which date is next or last.
 */
export function earningsOn(
  events: readonly InstrumentEvent[],
  date: string | null,
): EarningsReport | null {
  if (!date) return null;
  const found = events.find((e) => KINDS[e.kind] === 'earnings' && e.date === date.slice(0, 10));
  if (!found) return null;
  const v = valuesOf(found);
  const surprise = num(v['surprise_pct']);
  return {
    quarter: str(v['fiscal_quarter']) || null,
    epsForecast: num(v['eps_forecast']),
    epsReported: num(v['eps_reported']),
    surprise: surprise === null ? null : surprise / 100,
    reported: v['reported'] === true,
  };
}
