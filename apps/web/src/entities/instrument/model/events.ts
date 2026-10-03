/**
 * Instrument events (rows of every `events/*` table) as one timeline and as chart markers:
 * each kind (earnings, dividend, split, ticker / reference change) with a plain-English detail.
 */
import { formatValue, type ChartEvent } from '@algotrade/ui';

import type { components } from '@/shared/api';

export type InstrumentEvent = components['schemas']['InstrumentEvent'];

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
  'events/earnings': 'earnings',
  'events/dividend': 'dividend',
  'events/split': 'split',
  'events/reference_change': 'change',
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

function earningsDetail(v: Readonly<Record<string, unknown>>): string {
  const parts = [str(v['fiscal_quarter']) ? `Quarter ${str(v['fiscal_quarter'])}` : ''];
  const time = str(v['time']);
  if (time && time !== 'unknown')
    parts.push(time === 'pre' ? 'before the open' : 'after the close');
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
      const kind = KINDS[event.table] ?? 'other';
      return {
        id: `${event.table}-${event.ts}-${i}`,
        date: event.ts.slice(0, 10),
        kind,
        label: kind === 'other' ? event.table.replace('events/', '') : LABELS[kind],
        detail: detailOf(kind, event.values),
      };
    })
    .sort((a, b) => (a.date === b.date ? a.id.localeCompare(b.id) : b.date.localeCompare(a.date)));
}

/** Dividend, split and earnings markers for the price chart, oldest first. */
export function toChartEvents(events: readonly InstrumentEvent[]): ChartEvent[] {
  return toTimeline(events)
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
