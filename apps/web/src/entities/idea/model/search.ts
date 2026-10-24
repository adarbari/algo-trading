/**
 * The Ideas page's own state in the URL's search params: the column set in use. The filters in
 * force are the shared filter bar's `f` parameter (ADR 0082; `features/filter-bar`), composed
 * with this in the route. Absent keys mean the defaults.
 */

/** The column sets of the table: stock facts (default), or the options set (volatility, expiry, best put). */
export const IDEA_COLUMN_SETS = [
  { id: 'stocks', label: 'Stocks columns' },
  { id: 'options', label: 'Options columns' },
] as const;

export type IdeaColumnSet = (typeof IDEA_COLUMN_SETS)[number]['id'];

/** The raw search params this page owns (what the URL holds). */
export interface IdeasSearch {
  /** The column set in use (absent: stocks). */
  columns?: IdeaColumnSet;
}

/** A change to the params: `undefined` removes a key. */
export type IdeasSearchPatch = { [K in keyof IdeasSearch]: IdeasSearch[K] | undefined };

/** Validates the router's parsed search params (unknown keys and bad values are dropped). */
export function parseIdeasSearch(raw: Record<string, unknown>): IdeasSearch {
  const columns = IDEA_COLUMN_SETS.find((c) => c.id === raw['columns'])?.id;
  return columns && columns !== 'stocks' ? { columns } : {};
}
