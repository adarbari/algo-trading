/**
 * Explore's state in the URL's search params, so a view is a shareable link: the compare set,
 * the focused ticker, the tab, the table's columns, filters and sort, and each tab's choices.
 * Lists are comma-separated; absent keys take the defaults below.
 */
import type { ChartRange, DataTableSort } from '@algotrade/ui';

export const EXPLORE_TABS = [
  'overview',
  'compare',
  'chart',
  'options',
  'features',
  'events',
  'hits',
] as const;
export type ExploreTab = (typeof EXPLORE_TABS)[number];

/** The raw search params (what the URL holds). */
export interface ExploreSearch {
  /** The compare set: tickers, comma-separated, in pick order. */
  sel?: string;
  /** The ticker the detail tabs show (default: the first of the compare set). */
  focus?: string;
  tab?: ExploreTab;
  /** Ticker table columns: catalogue feature names, comma-separated. */
  cols?: string;
  /** Sort: a column id, `-` prefix for descending. */
  sort?: string;
  q?: string;
  type?: string;
  sector?: string;
  liq?: string;
  lev?: boolean;
  opt?: boolean;
  range?: ChartRange;
  /** Compare dimensions: catalogue feature names, comma-separated. */
  dims?: string;
  expiry?: string;
  view?: 'simple' | 'pro';
  right?: 'P' | 'C';
  strikes?: 'all';
  /** The feature whose distribution the Features tab shows. */
  feature?: string;
}

/** The mockup's columns: close, our IV30, IV / HV, distance from the 52-week high, earnings. */
export const DEFAULT_COLUMNS: readonly string[] = [
  'rollup.price_stats@v2.close',
  'rollup.iv30@v1.iv30',
  'feature.iv_hv_ratio',
  'feature.pct_from_high_52w',
  'rollup.earnings@v1.days_to_earnings',
];

export const DEFAULT_DIMENSIONS: readonly string[] = [
  'rollup.price_stats@v2.close',
  'rollup.iv30@v1.iv30',
  'rollup.price_stats@v2.hv30',
  'feature.iv_hv_spread',
  'feature.pct_from_high_52w',
  'rollup.price_stats@v2.adv_usd_20d',
  'feature.market_cap',
  'feature.div_yield',
  'rollup.earnings@v1.days_to_earnings',
];

const RANGES: readonly ChartRange[] = ['3M', '1Y', '2Y', 'All'];

const text = (value: unknown): string | undefined => {
  if (typeof value === 'string') return value.trim() || undefined;
  if (typeof value === 'number') return String(value);
  return undefined;
};

const flag = (value: unknown): boolean | undefined =>
  value === true || value === 'true'
    ? true
    : value === false || value === 'false'
      ? false
      : undefined;

const oneOf = <T extends string>(options: readonly T[], value: unknown): T | undefined =>
  options.find((o) => o === value);

/** Validates the router's parsed search params (unknown keys and bad values are dropped). */
export function parseExploreSearch(raw: Record<string, unknown>): ExploreSearch {
  const out: ExploreSearch = {};
  const set = <K extends keyof ExploreSearch>(key: K, value: ExploreSearch[K] | undefined) => {
    if (value !== undefined) out[key] = value;
  };
  set('sel', text(raw['sel'])?.toUpperCase());
  set('focus', text(raw['focus'])?.toUpperCase());
  set('tab', oneOf(EXPLORE_TABS, raw['tab']));
  set('cols', text(raw['cols']));
  set('sort', text(raw['sort']));
  set('q', text(raw['q']));
  set('type', text(raw['type']));
  set('sector', text(raw['sector']));
  set('liq', text(raw['liq']));
  set('lev', flag(raw['lev']));
  set('opt', flag(raw['opt']));
  set('range', oneOf(RANGES, raw['range']));
  set('dims', text(raw['dims']));
  set('expiry', text(raw['expiry']));
  set('view', oneOf(['simple', 'pro'] as const, raw['view']));
  set('right', oneOf(['P', 'C'] as const, raw['right']));
  set('strikes', oneOf(['all'] as const, raw['strikes']));
  set('feature', text(raw['feature']));
  return out;
}

/** An empty list in the URL (an absent key means the default list). */
export const NONE = 'none';

/** `"a, b,,c"` -> `["a", "b", "c"]`; `"none"` -> `[]`. */
export function splitList(value: string | undefined): string[] {
  if (value === NONE) return [];
  return (value ?? '')
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);
}

/** A list for the URL: undefined when it equals the default (so links stay short). */
export function joinList(
  values: readonly string[],
  defaults: readonly string[] = [],
): string | undefined {
  if (values.length === defaults.length && values.every((v, i) => v === defaults[i])) {
    return undefined;
  }
  return values.length === 0 ? NONE : values.join(',');
}

export function parseSort(value: string | undefined): DataTableSort | null {
  if (!value) return null;
  const desc = value.startsWith('-');
  return { columnId: desc ? value.slice(1) : value, direction: desc ? 'desc' : 'asc' };
}

export function formatSort(sort: DataTableSort | null): string | undefined {
  if (!sort) return undefined;
  return `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}`;
}
