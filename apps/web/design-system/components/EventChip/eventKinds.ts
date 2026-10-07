/**
 * The vocabulary of an event for the event-sensitivity components (EventChip, EventTimeline,
 * ExpiryLadder, CalendarGrid): the five kinds, the shape of one event item and the words for
 * its kind and time. The item mirrors the read model's event (date, time, kind, label, source,
 * known-from) in plain props, so the design system imports no API types.
 */

/** What an event is: own earnings, the reference name's earnings (a leveraged / inverse fund), a macro release, a market-structure day (expiry, index rebalance, quarter end) or a filing. */
export const EVENT_KINDS = [
  'own_earnings',
  'reference_earnings',
  'macro_release',
  'market_structure',
  'filing',
] as const;

export type EventKind = (typeof EVENT_KINDS)[number];

/** One dated event, as the API serves it. */
export interface EventItem {
  /** The calendar day, ISO (`2026-10-14`). */
  date: string;
  /** When on the day: `pre_market`, `intraday`, `after_hours`, `unknown` or a release time (`08:30`). */
  time: string;
  kind: EventKind;
  /** The short text the chip carries ("Earnings", "CPI", "FOMC", "Opex", "2.02 results"). */
  label: string;
  /** Where the date comes from ("Company calendar", "BLS", "SEC EDGAR"). */
  source: string;
  /** The day (or instant) from which the event was known, ISO: the point-in-time read bound. */
  knownFrom: string;
}

/** The kind in words: the screen-reader prefix of a chip and the legend text. */
export const EVENT_KIND_NAMES: Record<EventKind, string> = {
  own_earnings: 'Earnings',
  reference_earnings: 'Reference earnings',
  macro_release: 'Macro release',
  market_structure: 'Market structure',
  filing: 'Filing',
};

const TIME_WORDS: Record<string, string> = {
  pre_market: 'before the open',
  intraday: 'during the session',
  after_hours: 'after the close',
  unknown: 'time unknown',
};

/** A time code in words (`after_hours` -> "after the close"); a release time reads as it is. */
export function timeText(time: string): string {
  return TIME_WORDS[time] ?? time;
}
