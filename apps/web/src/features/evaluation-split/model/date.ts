/** Reading the date the user types: a calendar date as YYYY-MM-DD, nothing else. */

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

/** The message for text that is not a real calendar date, or null when it is one. */
export function dateError(text: string): string | null {
  const match = ISO.exec(text);
  if (match === null) return 'Use the form 2026-04-01.';
  const [, year, month, day] = match.map(Number);
  const probe = new Date(Date.UTC(year ?? 0, (month ?? 1) - 1, day ?? 1));
  const real =
    probe.getUTCFullYear() === year &&
    probe.getUTCMonth() === (month ?? 1) - 1 &&
    probe.getUTCDate() === day;
  return real ? null : 'That is not a calendar date.';
}

/** The message when `text` is after `latest` (the latest stored session), else null. */
export function afterLatest(text: string, latest: string): string | null {
  return text > latest ? `No stored session after ${latest}.` : null;
}
