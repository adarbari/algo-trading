/**
 * Where things are in the Guide and where the Guide sends the user: the one place that builds
 * these paths, so a page, a widget and the route tree agree. A name in a path is encoded
 * (catalogue names hold "@" and ".").
 */

export const GUIDE_PATH = '/guide';
export const GUIDE_START_PATH = '/guide/start';
export const GUIDE_GLOSSARY_PATH = '/guide/glossary';
export const GUIDE_FIELDS_PATH = '/guide/fields';
export const GUIDE_PLAYBOOKS_PATH = '/guide/playbooks';
export const GUIDE_SITUATIONS_PATH = '/guide/situations';
export const GUIDE_REGIME_PATH = '/guide/regime';

/** Today's readings: the Regime page in the Trader workspace. */
export const REGIME_PAGE_PATH = '/regime';

/** The sections that have pages, by the id `Query.guideIndex` gives them (the server orders them). */
export const BUILT_SECTIONS: readonly string[] = [
  'start',
  'regime',
  'playbooks',
  'fields',
  'situations',
  'glossary',
];

/** A Start here page (its id is the page's in `start.toml`). */
export function startPath(id: string): string {
  return `${GUIDE_START_PATH}/${encodeURIComponent(id)}`;
}

/** A glossary term's page. */
export function termPath(id: string): string {
  return `${GUIDE_GLOSSARY_PATH}/${encodeURIComponent(id)}`;
}

/** A regime indicator's page (its key is the card's). */
export function indicatorPath(key: string): string {
  return `${GUIDE_REGIME_PATH}/indicators/${encodeURIComponent(key)}`;
}

/** A reference market fall's page (its key is the episode's slug). */
export function episodePath(key: string): string {
  return `${GUIDE_REGIME_PATH}/episodes/${encodeURIComponent(key)}`;
}

/** A playbook's page (the id is the site preset's). */
export function playbookPath(id: string): string {
  return `${GUIDE_PLAYBOOKS_PATH}/${encodeURIComponent(id)}`;
}

/** A situation's page. */
export function situationPath(slug: string): string {
  return `${GUIDE_SITUATIONS_PATH}/${encodeURIComponent(slug)}`;
}

/** A screener's results (what "See today's hits" opens). */
export function screenerResultsPath(id: string): string {
  return `/screeners/${encodeURIComponent(id)}`;
}

/** A screener in the Builder. */
export function screenerBuilderPath(id: string): string {
  return `/screeners/${encodeURIComponent(id)}/edit`;
}

/**
 * The page of a Guide entry by the `kind` and `id` the server gives (a search result, a link in
 * a Start here page): start, indicator, episode, playbook, field, situation or term. An
 * unknown kind opens the Guide's home.
 */
export function guideEntryPath(kind: string, id: string): string {
  switch (kind) {
    case 'start':
      return startPath(id);
    case 'indicator':
      return indicatorPath(id);
    case 'episode':
      return episodePath(id);
    case 'playbook':
      return playbookPath(id);
    case 'field':
      return fieldPath(id);
    case 'situation':
      return situationPath(id);
    case 'term':
      return termPath(id);
    default:
      return GUIDE_PATH;
  }
}

/** What each kind of entry is called where entries are grouped (search results, links). */
export const GUIDE_KIND_TITLES: Readonly<Record<string, string>> = {
  start: 'Start here',
  indicator: 'Warning signs',
  episode: 'Market falls',
  playbook: 'Playbooks',
  field: 'Fields',
  situation: 'Situations',
  term: 'Glossary',
};

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
