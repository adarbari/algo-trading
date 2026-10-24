/**
 * The filter list's one search parameter, `f`, for a route's `validateSearch`: a non-empty
 * string with at least one `id:body` entry is kept as written, anything else is dropped. The
 * route's validator runs in the app's entry chunk on every page, so it stays this small: the
 * codec (`decodeFilters` / `encodeFilters`) loads with the page that reads the filters, which
 * ignores malformed entries when it decodes and writes the canonical spelling with its next change.
 */

/** The raw search params the filter bar owns. */
export interface FilterSearch {
  f?: string;
}

/** Validates the router's parsed search params; merge the result into a route's own validator. */
export function filterSearch(raw: Record<string, unknown>): FilterSearch {
  const value = raw['f'];
  const f = typeof value === 'string' ? value.trim() : '';
  return f.includes(':') ? { f } : {};
}
