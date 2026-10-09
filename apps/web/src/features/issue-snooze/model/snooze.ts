/**
 * Snoozing a status issue for 24 hours, per viewer: a map from issue id to the time the snooze
 * ends, in localStorage (guarded: storage can throw or be empty, and then a snooze lasts only
 * this page load). Pure helpers plus the guarded read and write; an expired entry is dropped,
 * and an issue whose id changed is a different issue, so it shows.
 */
export const SNOOZE_MS = 24 * 60 * 60 * 1000;

const KEY = 'algotrade.snoozedIssues';

export type Snoozes = Readonly<Record<string, number>>;

/** The stored map, keeping only well-formed entries that have not ended by `now`. */
export function parseSnoozes(raw: string | null, now: number): Snoozes {
  if (raw === null) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, number] => typeof entry[1] === 'number' && entry[1] > now,
      ),
    );
  } catch {
    return {};
  }
}

/** The map with `id` snoozed from `now`. */
export function withSnooze(snoozes: Snoozes, id: string, now: number): Snoozes {
  return { ...snoozes, [id]: now + SNOOZE_MS };
}

export function loadSnoozes(now: number): Snoozes {
  try {
    return parseSnoozes(localStorage.getItem(KEY), now);
  } catch {
    return {};
  }
}

export function saveSnoozes(snoozes: Snoozes): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(snoozes));
  } catch {
    // Storage unavailable: the in-memory map still hides the issue for this page load.
  }
}
