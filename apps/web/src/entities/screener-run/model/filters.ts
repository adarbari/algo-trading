/**
 * The narrowing the Screener runs list sends to the server (user, screener, status): the
 * search parameters it lives in. The status is the API's `RunStatus` enum (its values are
 * listed in `labels.ts` from the generated type, never copied). The server filters; nothing is
 * counted or re-ranked here.
 */
import { RUN_STATUSES, type RunStatus } from './labels';

export interface ScreenerRunFilters {
  user?: string | undefined;
  screener?: string | undefined;
  status?: RunStatus | undefined;
}

const text = (value: unknown): string | undefined =>
  typeof value === 'string' && value.trim() ? value.trim() : undefined;

/** A status word in a URL (any case) as the enum's value; anything else is dropped. */
const status = (value: unknown): RunStatus | undefined => {
  const word = text(value)?.toUpperCase();
  return RUN_STATUSES.find((s) => s === word);
};

/** The filters in a URL's search object: a text value kept, anything else dropped. */
export function parseFilters(search: {
  user?: unknown;
  screener?: unknown;
  status?: unknown;
}): ScreenerRunFilters {
  const user = text(search.user);
  const screener = text(search.screener);
  const run = status(search.status);
  return {
    ...(user ? { user } : {}),
    ...(screener ? { screener } : {}),
    ...(run ? { status: run } : {}),
  };
}
