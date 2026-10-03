/**
 * Is the data a screen shows stale? The nightly run stores each session the next morning, so
 * a session more than a long weekend (4 calendar days) before today means a run was missed.
 */
import { daysBetween, todayIso } from '@/shared/lib';

export const STALE_AFTER_DAYS = 4;

export function isStale(session: string, today: string = todayIso()): boolean {
  return daysBetween(session, today) > STALE_AFTER_DAYS;
}
