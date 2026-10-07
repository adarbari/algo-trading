/**
 * Sample calendars for CalendarGrid's stories and tests: a handful of names over the days
 * around Fri 2 Oct 2026, and a generated many-name calendar for paging. Not real data.
 */
import { dayAfter, type SampleEvent } from './eventSamples';

/** One event of the cross-name calendar: an event and its name. */
export interface SampleCalendarEvent extends SampleEvent {
  instrumentId: string;
  symbol: string;
}

export interface SampleCalendarDay {
  date: string;
  events: SampleCalendarEvent[];
}

export interface SampleName {
  id: string;
  symbol: string;
}

const at = (
  instrumentId: string,
  symbol: string,
  event: Omit<SampleEvent, 'source' | 'knownFrom'> & Partial<SampleEvent>,
): SampleCalendarEvent => ({
  source: 'Company calendar',
  knownFrom: '2026-09-18',
  instrumentId,
  symbol,
  ...event,
});

export const names: SampleName[] = [
  { id: 'EQ:NVDA', symbol: 'NVDA' },
  { id: 'EQ:AAPL', symbol: 'AAPL' },
  { id: 'EQ:TSLA', symbol: 'TSLA' },
  { id: 'EQ:MSFT', symbol: 'MSFT' },
];

const calendar: SampleCalendarEvent[] = [
  at('EQ:AAPL', 'AAPL', {
    date: '2026-10-29',
    time: 'after_hours',
    kind: 'own_earnings',
    label: 'Earnings',
  }),
  at('EQ:MSFT', 'MSFT', {
    date: '2026-10-28',
    time: 'after_hours',
    kind: 'own_earnings',
    label: 'Earnings',
  }),
  at('EQ:TSLA', 'TSLA', {
    date: '2026-10-21',
    time: 'after_hours',
    kind: 'own_earnings',
    label: 'Earnings',
  }),
  at('EQ:NVDA', 'NVDA', {
    date: '2026-11-18',
    time: 'after_hours',
    kind: 'own_earnings',
    label: 'Earnings',
  }),
  ...names.flatMap((n) => [
    at(n.id, n.symbol, {
      date: '2026-10-14',
      time: '08:30',
      kind: 'macro_release',
      label: 'CPI',
      source: 'BLS',
    }),
    at(n.id, n.symbol, {
      date: '2026-10-28',
      time: '14:00',
      kind: 'macro_release',
      label: 'FOMC',
      source: 'Federal Reserve',
    }),
  ]),
  at('EQ:NVDA', 'NVDA', {
    date: '2026-10-28',
    time: 'after_hours',
    kind: 'reference_earnings',
    label: 'MSFT earnings',
  }),
  at('EQ:TSLA', 'TSLA', {
    date: '2026-10-09',
    time: 'after_hours',
    kind: 'filing',
    label: '2.02 results',
    source: 'SEC EDGAR',
  }),
];

/** Days with events, oldest first, from the sample calendar. */
export function daysOf(events: readonly SampleCalendarEvent[]): SampleCalendarDay[] {
  const dates = [...new Set(events.map((e) => e.date))].sort();
  return dates.map((date) => ({ date, events: events.filter((e) => e.date === date) }));
}

/** The expiry Fridays inside the sample window. */
export const expiryFridays = ['2026-10-16', '2026-11-20'];

/** The sample days plus the expiry Fridays (empty days: the API lists a ruled day even with no event that day). */
export const sampleDays: SampleCalendarDay[] = [
  ...daysOf(calendar),
  ...expiryFridays.map((date) => ({ date, events: [] })),
].sort((a, b) => a.date.localeCompare(b.date));

/** `count` names with an earnings date each, spread over the next weeks (paging, density). */
export function manyNames(count: number): { names: SampleName[]; days: SampleCalendarDay[] } {
  const list = Array.from({ length: count }, (_, i): SampleName => {
    const symbol = `SYM${String(i + 1).padStart(2, '0')}`;
    return { id: `EQ:${symbol}`, symbol };
  });
  const events = list.map((n, i) =>
    at(n.id, n.symbol, {
      date: dayAfter(7 + ((i * 5) % 40)),
      time: i % 2 === 0 ? 'pre_market' : 'after_hours',
      kind: 'own_earnings',
      label: 'Earnings',
    }),
  );
  return { names: list, days: daysOf(events) };
}
