/**
 * Calendar-day arithmetic on ISO days (`2026-10-02`), in UTC so a date never shifts with the
 * viewer's time zone. Trading sessions are the API's business; this only counts days.
 */

const DAY_MS = 86_400_000;

const parse = (iso: string): Date => new Date(`${iso.slice(0, 10)}T00:00:00Z`);

/** Today's calendar day in UTC, `2026-10-03`. */
export function todayIso(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

/** `iso` moved by `months` (negative: back), clamped like `Date.setUTCMonth`. */
export function addMonths(iso: string, months: number): string {
  const date = parse(iso);
  date.setUTCMonth(date.getUTCMonth() + months);
  return date.toISOString().slice(0, 10);
}

/** `iso` moved by `days` (negative: back). */
export function addDays(iso: string, days: number): string {
  return new Date(parse(iso).getTime() + days * DAY_MS).toISOString().slice(0, 10);
}

/** Whole calendar days from `from` to `to` (negative when `to` is earlier). */
export function daysBetween(from: string, to: string): number {
  return Math.round((parse(to).getTime() - parse(from).getTime()) / DAY_MS);
}
