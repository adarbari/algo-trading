/**
 * The narrowing the Screener runs list sends to the server (user, screener, status): the
 * search parameters it lives in, and the statuses a run record can hold. The server filters;
 * nothing is counted or re-ranked here.
 */

/** A run record's statuses (the server's words; each has its Guide entry). */
export const RUN_STATUSES = [
  'queued',
  'running',
  'complete',
  'partial',
  'waiting',
  'failed',
] as const;

export interface ScreenerRunFilters {
  user?: string | undefined;
  screener?: string | undefined;
  status?: string | undefined;
}

const text = (value: unknown): string | undefined =>
  typeof value === 'string' && value.trim() ? value.trim() : undefined;

/** The filters in a URL's search object: a text value kept, anything else dropped. */
export function parseFilters(search: {
  user?: unknown;
  screener?: unknown;
  status?: unknown;
}): ScreenerRunFilters {
  const user = text(search.user);
  const screener = text(search.screener);
  const status = text(search.status);
  return {
    ...(user ? { user } : {}),
    ...(screener ? { screener } : {}),
    ...(status ? { status } : {}),
  };
}
