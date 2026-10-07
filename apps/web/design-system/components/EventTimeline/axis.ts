/**
 * The timeline's axis arithmetic: where a day sits in the window (a fraction of its width), the
 * month starts inside it, and the events grouped by day. Pure functions over ISO days; the
 * window and the events come from the caller (nothing is derived from data the caller did not
 * give).
 */
import type { EventItem } from '../EventChip';

const toMs = (iso: string) => Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);

/** Where `date` sits in the window `start`..`end`: 0 at the start, 1 at the end (an equal start and end reads 0). */
export function fraction(date: string, start: string, end: string): number {
  const span = toMs(end) - toMs(start);
  if (span <= 0) return 0;
  return Math.min(1, Math.max(0, (toMs(date) - toMs(start)) / span));
}

/** The first days of the months inside the window (ISO), after the window's own first day. */
export function monthStarts(start: string, end: string): string[] {
  const out: string[] = [];
  const first = new Date(toMs(start));
  let cursor = Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 1);
  while (cursor <= toMs(end)) {
    out.push(new Date(cursor).toISOString().slice(0, 10));
    const next = new Date(cursor);
    cursor = Date.UTC(next.getUTCFullYear(), next.getUTCMonth() + 1, 1);
  }
  return out;
}

/** The days in the window with their events, oldest day first; the events keep the caller's order within a day. */
export function groupByDay(
  events: readonly EventItem[],
  start: string,
  end: string,
): { date: string; events: EventItem[] }[] {
  const lo = toMs(start);
  const hi = toMs(end);
  const days = new Map<string, EventItem[]>();
  for (const event of events) {
    const at = toMs(event.date);
    if (at < lo || at > hi) continue;
    days.set(event.date, [...(days.get(event.date) ?? []), event]);
  }
  return [...days.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([date, list]) => ({ date, events: list }));
}
