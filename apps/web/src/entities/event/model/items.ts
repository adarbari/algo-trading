/**
 * The event study and the calendar as the design system's event components take them
 * (`EventItem`, expiry rows, calendar days) and as chart markers: a change of shape only. Every
 * label, `clear` and `marked` is the API's; nothing is counted, dated or classified here
 * (ADR 0038). Pure.
 */
import {
  EVENT_KINDS,
  timeText,
  type CalendarDay,
  type CalendarName,
  type ChartEvent,
  type EventItem,
  type EventKind,
  type ExpiryRow,
} from '@algotrade/ui';

import type { EventCalendarResponse } from '../api/calendar';
import type { EventStudyResponse } from '../api/study';

import { unknownLabel } from '@/entities/feature';

/** A dated event as `eventStudy.ahead` / `eventCalendar` select it. */
export interface AheadShape {
  date: string;
  time: string;
  kind: string;
  label: string;
  source: string;
  knownFrom?: string | null | undefined;
}

type Study = NonNullable<EventStudyResponse['instrument']>['eventStudy'];
type Defined<T> = NonNullable<T>;
export type StudyFiling = Defined<Study>['filings'][number];
export type StudyGap = Defined<Study>['gaps'][number];
export type StudyRung = Defined<Study>['ladder'][number];

const isKind = (kind: string): kind is EventKind =>
  (EVENT_KINDS as readonly string[]).includes(kind);

/**
 * One event as an `EventItem`; null for a kind the design system has no chip for. A row with no
 * `knownFrom` (a catalogue value or a calendar rule) is known as of `session`, the read's own.
 */
export function eventItem(event: AheadShape, session: string): EventItem | null {
  if (!isKind(event.kind)) return null;
  return {
    date: event.date,
    time: event.time,
    kind: event.kind,
    label: event.label,
    source: event.source,
    knownFrom: event.knownFrom ?? session,
  };
}

const present = <T>(items: readonly (T | null)[]): T[] => items.filter((i): i is T => i !== null);

/** The events ahead, oldest first as the API sends them. */
export function aheadItems(study: Defined<Study>): EventItem[] {
  return present(study.ahead.map((e) => eventItem(e, study.session)));
}

/** A filing as an event item: its label is the API's words for the first item. */
export function filingItem(filing: StudyFiling): EventItem {
  return {
    date: filing.filingDate,
    time: `${filing.accepted.slice(11, 16)} UTC`,
    kind: 'filing',
    label: filing.label,
    source: 'SEC EDGAR',
    knownFrom: filing.knownFrom,
  };
}

/** The expiry ladder's rows: `marked` is the design system's `firstClear`. */
export function ladderRows(study: Defined<Study>): ExpiryRow[] {
  return study.ladder.map((rung) => ({
    expiry: rung.expiry,
    dte: rung.days,
    events: present(rung.spans.map((e) => eventItem(e, study.session))),
    clear: rung.clear,
    firstClear: rung.marked,
  }));
}

const PARTS: Readonly<Record<string, string>> = {
  own_earnings: 'Earnings date',
  reference_earnings: 'Reference earnings date',
  macro_release: 'Macro releases',
  reference: 'Fund reference',
  filings: 'Filings',
  ladder: 'Expiry ladder',
};

/** One line per part not known for the session: the part, the server's word and its detail. */
export function gapLines(gaps: readonly StudyGap[]): string[] {
  const lines = gaps.map(({ part, unknown }) => {
    const what = unknownLabel(unknown.code, unknown.reason);
    const detail = unknown.detail ? ` (${unknown.detail})` : '';
    return `${PARTS[part] ?? part.replace(/_/g, ' ')}: ${what}${detail}`;
  });
  // Two gaps can read the same (one table missing for several parts): one line each, so a
  // list keyed by the line stays unique.
  return [...new Set(lines)];
}

/**
 * Markers for the price chart from the same study: the own earnings and macro dates ahead and
 * the filings, oldest first. Earnings dates the stored events already mark are left to them.
 */
export function studyChartEvents(
  study: Defined<Study>,
  alreadyMarked: ReadonlySet<string>,
): ChartEvent[] {
  const ahead = study.ahead.flatMap((e): ChartEvent[] => {
    if (e.kind === 'own_earnings' && !alreadyMarked.has(e.date)) {
      return [{ time: e.date, kind: 'earnings', detail: timeText(e.time) }];
    }
    if (e.kind === 'macro_release') {
      return [{ time: e.date, kind: 'macro', detail: `${e.label} ${e.time}` }];
    }
    return [];
  });
  const filings = study.filings.map((f): ChartEvent => ({
    time: f.filingDate,
    kind: 'filing',
    detail: `${f.form} ${f.label}`,
  }));
  return [...filings, ...ahead].sort((a, b) => a.time.localeCompare(b.time));
}

/** The id and word of the column that holds the market-wide events (macro, expiry). */
export const MARKET_NAME: CalendarName = { id: 'MARKET', symbol: 'Market' };

/**
 * The calendar's days for `CalendarGrid`: a market-wide event (no name) sits in the Market
 * column. `names` lists the Market column first when any event is market-wide.
 */
export function calendarDays(calendar: EventCalendarResponse): {
  days: CalendarDay[];
  names: CalendarName[];
  ruledDays: string[];
} {
  const days = calendar.days.map((day) => ({
    date: day.date,
    events: day.events.flatMap((e) => {
      const item = eventItem(e.event, calendar.session);
      if (!item) return [];
      return [
        {
          ...item,
          instrumentId: e.instrumentId ?? MARKET_NAME.id,
          symbol: e.symbol ?? MARKET_NAME.symbol,
        },
      ];
    }),
  }));
  const marketWide = days.some((d) => d.events.some((e) => e.instrumentId === MARKET_NAME.id));
  const named = calendar.names.map((n) => ({ id: n.instrumentId, symbol: n.symbol }));
  const ruledDays = calendar.days
    .filter((d) => d.events.some((e) => e.event.expiry))
    .map((d) => d.date);
  return { days, names: marketWide ? [MARKET_NAME, ...named] : named, ruledDays };
}
