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

/** The Ideas tabs (ADR 0083 amendment (a)): the URL's `tab`, Stocks when absent. */
export const IDEA_TABS = [
  { id: 'stocks', label: 'Stocks' },
  { id: 'premium', label: 'Premium' },
] as const;

export type IdeaTab = (typeof IDEA_TABS)[number]['id'];

/** The API's enum value of a tab. */
export const gqlTab = (tab: IdeaTab): 'STOCKS' | 'PREMIUM' =>
  tab === 'premium' ? 'PREMIUM' : 'STOCKS';

/** The raw search params this page owns (what the URL holds). */
export interface IdeasSearch {
  /** The tab (absent: stocks). */
  tab?: IdeaTab;
  /** The column set in use (absent: stocks). */
  columns?: IdeaColumnSet;
}

/** A change to the params: `undefined` removes a key. */
export type IdeasSearchPatch = { [K in keyof IdeasSearch]: IdeasSearch[K] | undefined };

/** Validates the router's parsed search params (unknown keys and bad values are dropped). */
export function parseIdeasSearch(raw: Record<string, unknown>): IdeasSearch {
  const columns = IDEA_COLUMN_SETS.find((c) => c.id === raw['columns'])?.id;
  const tab = raw['tab'] === 'premium' ? 'premium' : undefined;
  return {
    ...(tab && { tab }),
    ...(columns && columns !== 'stocks' && { columns }),
  };
}
