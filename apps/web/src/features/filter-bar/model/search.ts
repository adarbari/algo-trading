/**
 * The filter list's one search parameter, `f`, for a route's `validateSearch`: a string that
 * decodes to at least one filter, written back in its canonical form (so a hand-edited or
 * stale link settles to one spelling); anything else is dropped.
 */
import { decodeFilters, encodeFilters } from './codec';

/** The raw search params the filter bar owns. */
export interface FilterSearch {
  f?: string;
}

/** Validates the router's parsed search params; merge the result into a route's own validator. */
export function filterSearch(raw: Record<string, unknown>): FilterSearch {
  const value = raw['f'];
  if (typeof value !== 'string') return {};
  const canonical = encodeFilters(decodeFilters(value));
  return canonical ? { f: canonical } : {};
}
