/**
 * Where things are in the Guide and where the Guide sends the user: the one place that builds
 * these paths, so a page, a widget and the route tree agree. A name in a path is encoded
 * (catalogue names hold "@" and ".").
 */

export const GUIDE_PATH = '/guide';
export const GUIDE_FIELDS_PATH = '/guide/fields';

/** The sections that have pages today, by the id `Query.guideIndex` gives them. */
export const BUILT_SECTIONS: readonly string[] = ['fields'];

/** The views of the field index. */
export type FieldsView = 'theme' | 'intent' | 'az';

export interface FieldsSearch {
  view?: FieldsView;
  theme?: string;
  intent?: string;
}

/** A field's page. */
export function fieldPath(name: string): string {
  return `${GUIDE_FIELDS_PATH}/${encodeURIComponent(name)}`;
}

/** The field index in one view, optionally narrowed to one theme or intent. */
export function fieldsPath(search: FieldsSearch = {}): string {
  const params = new URLSearchParams();
  if (search.view) params.set('view', search.view);
  if (search.theme) params.set('theme', search.theme);
  if (search.intent) params.set('intent', search.intent);
  const query = params.toString();
  return query ? `${GUIDE_FIELDS_PATH}?${query}` : GUIDE_FIELDS_PATH;
}

/** Explore's Features tab on `symbol`, with `name`'s distribution and the ticker marked on it. */
export function exploreFieldPath(name: string, symbol: string): string {
  const params = new URLSearchParams({
    sel: symbol,
    focus: symbol,
    tab: 'features',
    feature: name,
  });
  return `/explore?${params.toString()}`;
}

/** A theme as a heading ("momentum and trend" -> "Momentum and trend"). */
export function themeTitle(theme: string): string {
  return theme.charAt(0).toUpperCase() + theme.slice(1);
}

/** Validates the field index's search params (unknown keys and bad values are dropped). */
export function parseFieldsSearch(raw: Record<string, unknown>): FieldsSearch {
  const text = (value: unknown) =>
    typeof value === 'string' && value.trim() !== '' ? value.trim() : undefined;
  const view = ['theme', 'intent', 'az'].find((v) => v === raw['view']) as FieldsView | undefined;
  const out: FieldsSearch = {};
  if (view) out.view = view;
  const theme = text(raw['theme']);
  if (theme) out.theme = theme;
  const intent = text(raw['intent']);
  if (intent) out.intent = intent;
  return out;
}
