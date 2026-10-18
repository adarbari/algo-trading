/**
 * Whether the panel's parallel requests were all answered for one session. Each request resolves
 * the latest session on its own, so a nightly publish between them can leave one part a session
 * ahead of another; the panel then shows its error state rather than two sessions side by side.
 * It only compares the dates the server sent.
 */

/** True when the answered requests name more than one session date (a pending one has none). */
export function sessionsDiffer(dates: readonly (string | null | undefined)[]): boolean {
  return new Set(dates.filter((date): date is string => Boolean(date))).size > 1;
}
