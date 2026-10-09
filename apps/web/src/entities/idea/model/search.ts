/**
 * The Ideas page's state in the URL's search params, so a view of the table is a shareable
 * link: the saved view in use (a preset) and the filter chips in force. Absent keys mean the
 * default view with no filter.
 */

export const IDEA_VIEWS = [
  { id: 'top', label: 'Top today' },
  { id: 'conviction', label: 'High conviction' },
  { id: 'no-earnings', label: 'No earnings soon' },
] as const;

export type IdeaViewId = (typeof IDEA_VIEWS)[number]['id'];

/** The filter chips, each a search key. */
export const IDEA_FILTER_KEYS = ['screener', 'decision', 'liq', 'regime'] as const;
export type IdeaFilterKey = (typeof IDEA_FILTER_KEYS)[number];

/** The liquidity chip's values: names with no liquidity-risk watch-out, or with one. */
export const LIQUIDITY_VALUES = ['ok', 'risk'] as const;

/** The raw search params (what the URL holds). */
export interface IdeasSearch {
  view?: IdeaViewId;
  /** A screener's config id: ideas it picked. */
  screener?: string;
  /** A best decision (`QUALIFIED`, ...). */
  decision?: string;
  liq?: (typeof LIQUIDITY_VALUES)[number];
  /** A regime label the pick was stamped with. */
  regime?: string;
}

/** A change to the params: `undefined` removes a key. */
export type IdeasSearchPatch = { [K in keyof IdeasSearch]: IdeasSearch[K] | undefined };

const text = (value: unknown): string | undefined =>
  typeof value === 'string' ? value.trim() || undefined : undefined;

const oneOf = <T extends string>(options: readonly T[], value: unknown): T | undefined =>
  options.find((o) => o === value);

/** Validates the router's parsed search params (unknown keys and bad values are dropped). */
export function parseIdeasSearch(raw: Record<string, unknown>): IdeasSearch {
  const out: IdeasSearch = {};
  const view = oneOf(
    IDEA_VIEWS.map((v) => v.id),
    raw['view'],
  );
  if (view && view !== 'top') out.view = view;
  const screener = text(raw['screener']);
  if (screener) out.screener = screener;
  const decision = text(raw['decision']);
  if (decision) out.decision = decision;
  const liq = oneOf(LIQUIDITY_VALUES, raw['liq']);
  if (liq) out.liq = liq;
  const regime = text(raw['regime']);
  if (regime) out.regime = regime;
  return out;
}

/** The filter chips in force. */
export function activeFilterKeys(search: IdeasSearch): IdeaFilterKey[] {
  return IDEA_FILTER_KEYS.filter((key) => search[key] !== undefined);
}
