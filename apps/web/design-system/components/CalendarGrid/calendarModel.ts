/**
 * The calendar grid's data model: the names axis (given, or the distinct names in the events),
 * the events looked up by day and name, and the page of names being shown. Pure functions over
 * the caller's days and events; nothing is derived from data the caller did not give.
 */
import type { EventItem } from '../EventChip';

/** One event of the cross-name calendar: an event item and the name it belongs to. */
export interface CalendarEvent extends EventItem {
  /** The instrument's id. */
  instrumentId: string;
  /** The ticker shown on the name axis. */
  symbol: string;
}

/** One day of the calendar with the events that fall on it. */
export interface CalendarDay {
  /** The calendar day, ISO. */
  date: string;
  events: readonly CalendarEvent[];
}

/** One name (instrument) of the grid. */
export interface CalendarName {
  id: string;
  symbol: string;
}

/** The names to show: the caller's list, else the distinct names in the events, in first-seen order. */
export function namesOf(
  days: readonly CalendarDay[],
  given: readonly CalendarName[] | undefined,
): CalendarName[] {
  if (given) return [...given];
  const seen = new Map<string, CalendarName>();
  for (const day of days) {
    for (const event of day.events) {
      if (!seen.has(event.instrumentId)) {
        seen.set(event.instrumentId, { id: event.instrumentId, symbol: event.symbol });
      }
    }
  }
  return [...seen.values()];
}

/** The events of each (day, name) cell, keyed by `cellKey`. */
export function cellsOf(days: readonly CalendarDay[]): Map<string, CalendarEvent[]> {
  const cells = new Map<string, CalendarEvent[]>();
  for (const day of days) {
    for (const event of day.events) {
      const key = cellKey(day.date, event.instrumentId);
      cells.set(key, [...(cells.get(key) ?? []), event]);
    }
  }
  return cells;
}

export const cellKey = (date: string, id: string) => `${date}|${id}`;

/** The `page`th slice of `size` names, with the page clamped to the pages that exist. */
export function pageOf<T>(items: readonly T[], page: number, size: number) {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(0, page), pages - 1);
  return {
    items: items.slice(current * size, (current + 1) * size),
    page: current,
    pages,
    from: items.length === 0 ? 0 : current * size + 1,
    to: Math.min(items.length, (current + 1) * size),
  };
}
