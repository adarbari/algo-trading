/**
 * Explore's state in the URL's search params, so a view is a shareable link: the open tickers
 * (`sel`), the one in focus, the tab, and each tab's choices. Lists are comma-separated; absent
 * keys take the defaults below.
 */
import type { ChartRange } from '@algotrade/ui';

import { feature } from '@/shared/api';

export const EXPLORE_TABS = [
  'overview',
  'compare',
  'chart',
  'options',
  'features',
  'events',
  'hits',
  'why',
] as const;
export type ExploreTab = (typeof EXPLORE_TABS)[number];

/** The raw search params (what the URL holds). */
export interface ExploreSearch {
  /** The open tickers (one tab each), comma-separated, in the order they were opened; also the
   * compare set. */
  sel?: string;
  /** The open ticker whose tab is selected (default: the first); a ticker not yet open opens. */
  focus?: string;
  tab?: ExploreTab;
  range?: ChartRange;
  /** Compare dimensions: catalogue feature names, comma-separated. */
  dims?: string;
  expiry?: string;
  view?: 'simple' | 'pro';
  right?: 'P' | 'C';
  strikes?: 'all';
  /** The feature whose distribution the Features tab shows. */
  feature?: string;
  /** The screener (config id) that surfaced the ticker, set when Ideas opens it. */
  via?: string;
}

export const DEFAULT_DIMENSIONS: readonly string[] = [
  feature('rollup.price_stats@v2.close'),
  feature('rollup.iv30@v1.iv30'),
  feature('rollup.price_stats@v2.hv30'),
  feature('feature.iv_hv_spread'),
  feature('feature.pct_from_high_avail'),
  feature('rollup.price_stats@v2.adv_usd_20d'),
  feature('feature.market_cap'),
  feature('feature.div_yield'),
  feature('rollup.earnings@v1.days_to_earnings'),
];

const RANGES: readonly ChartRange[] = ['3M', '1Y', '2Y', 'All'];

const text = (value: unknown): string | undefined => {
  if (typeof value === 'string') return value.trim() || undefined;
  if (typeof value === 'number') return String(value);
  return undefined;
};

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
  set('range', oneOf(RANGES, raw['range']));
  set('dims', text(raw['dims']));
  set('expiry', text(raw['expiry']));
  set('view', oneOf(['simple', 'pro'] as const, raw['view']));
  set('right', oneOf(['P', 'C'] as const, raw['right']));
  set('strikes', oneOf(['all'] as const, raw['strikes']));
  set('feature', text(raw['feature']));
  set('via', text(raw['via']));
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
