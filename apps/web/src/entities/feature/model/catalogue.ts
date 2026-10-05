/**
 * The feature catalogue as the web app reads it: one entry per selectable field (reference
 * facts, company details, rollup columns, expression features, the user's own), with how its
 * values read (a ValueFormat from the unit and dtype) and a short column label.
 */
import type { ValueFormat } from '@algotrade/ui';

import { feature, type components } from '@/shared/api';

export type CatalogueFeature = components['schemas']['Feature'];

/** Short labels for the features the Explore defaults show (the mockup's headers). */
const LABELS: Readonly<Record<string, string>> = {
  [feature('rollup.price_stats@v2.close')]: 'Close',
  [feature('rollup.iv30@v1.iv30')]: 'IV30',
  [feature('feature.iv_hv_ratio')]: 'IV/HV',
  [feature('feature.iv_hv_spread')]: 'IV − HV',
  [feature('feature.pct_from_high_52w')]: 'From high',
  [feature('rollup.earnings@v1.days_to_earnings')]: 'Earn.',
  [feature('rollup.price_stats@v2.hv30')]: 'HV30',
  [feature('rollup.price_stats@v2.adv_usd_20d')]: 'ADV 20d',
  [feature('feature.market_cap')]: 'Mkt cap',
  [feature('feature.div_yield')]: 'Div yield',
  [feature('feature.liquidity_class')]: 'Liquidity',
  [feature('instrument.sector')]: 'Sector',
  [feature('feature.vrp_iv30')]: 'IV30',
  [feature('feature.vrp_iv_hv_spread')]: 'IV − HV',
  [feature('feature.vrp_iv_hv_ratio')]: 'IV/HV',
  [feature('feature.dist_52w')]: 'Dist. 52w',
};

/** Longer names for the compare table's dimension column. */
const NAMES: Readonly<Record<string, string>> = {
  [feature('rollup.price_stats@v2.close')]: 'Last close',
  [feature('rollup.iv30@v1.iv30')]: 'IV30 (ours)',
  [feature('rollup.price_stats@v2.hv30')]: 'HV30',
  [feature('feature.iv_hv_spread')]: 'IV − HV',
  [feature('feature.pct_from_high_52w')]: 'From 52w high',
  [feature('rollup.price_stats@v2.adv_usd_20d')]: 'Avg dollar volume 20d',
  [feature('feature.market_cap')]: 'Market cap',
  [feature('feature.div_yield')]: 'Dividend yield',
  [feature('rollup.earnings@v1.days_to_earnings')]: 'Next earnings',
  [feature('feature.vrp_iv30')]: 'IV30',
  [feature('feature.vrp_iv_hv_spread')]: 'IV30 − HV30',
  [feature('feature.vrp_iv_hv_ratio')]: 'IV30 / HV30',
  [feature('feature.dist_52w')]: 'Distance to 52w high or low',
};

/** The column part of a field name: `rollup.iv30@v1.iv30` -> `iv30`. */
export function featureColumn(name: string): string {
  return name.slice(name.lastIndexOf('.') + 1);
}

/** `pct_from_high_52w` -> `Pct from high 52w`. */
function humanise(column: string): string {
  const words = column.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** A short header for a table column. */
export function featureLabel(name: string): string {
  return LABELS[name] ?? humanise(featureColumn(name));
}

/** A readable name for a row that names the feature (compare dimensions, feature list). */
export function featureTitle(name: string): string {
  return NAMES[name] ?? LABELS[name] ?? humanise(featureColumn(name));
}

/** The group a feature belongs to, for grouping a picker: `price_stats@v2`, `reference`, ... */
export function featureGroup(feature: CatalogueFeature): string {
  if (feature.scope === 'user') return 'Your features';
  if (feature.group) return feature.group;
  if (feature.name.startsWith('instrument.')) return 'Instrument';
  return 'Expression features';
}

/** A user's own feature (scope `user`): declared in their config, never shared. */
export function isOwn(feature: CatalogueFeature): boolean {
  return feature.scope === 'user';
}

/**
 * Derived from personal-use licensed market data (IBKR; ADR 0028): its values are shown to
 * the owner only, never shared or published.
 */
export function isPersonal(feature: CatalogueFeature): boolean {
  return feature.licence === 'personal';
}

/** The marks a feature carries in lists: "yours", "personal licence". */
export function featureMarks(feature: CatalogueFeature): string[] {
  return [
    ...(isOwn(feature) ? ['yours'] : []),
    ...(isPersonal(feature) ? ['personal licence'] : []),
  ];
}

const BY_UNIT: Readonly<Record<string, ValueFormat>> = {
  usd_per_share: { kind: 'currency' },
  usd: { kind: 'currency-compact' },
  decimal: { kind: 'percent' },
  pct_points: { kind: 'number', digits: 1 },
  ratio: { kind: 'number', digits: 2 },
  count: { kind: 'number' },
  shares: { kind: 'compact' },
  sessions: { kind: 'number' },
  days: { kind: 'number' },
  date: { kind: 'date' },
};

/** How a feature's values read: from its unit, else its dtype. */
export function featureFormat(feature: CatalogueFeature | undefined): ValueFormat {
  if (!feature) return { kind: 'text' };
  const byUnit = feature.unit ? BY_UNIT[feature.unit] : undefined;
  if (byUnit) return byUnit;
  if (feature.dtype === 'date') return { kind: 'date' };
  if (feature.dtype.startsWith('float')) return { kind: 'number', digits: 2 };
  if (feature.dtype.startsWith('int')) return { kind: 'number' };
  return { kind: 'text' };
}

/** Is the feature a number (a sparkline or a distribution can show it)? */
export function isNumericFeature(feature: CatalogueFeature | undefined): boolean {
  return Boolean(feature && /^(float|int)/.test(feature.dtype));
}

/** A cell value as the formatters expect it: booleans read Yes / No. */
export function displayValue(value: unknown): unknown {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return value;
}

/** The unit in words for a feature list ("usd per share" -> "$ / share"). */
export function unitLabel(unit: string | null | undefined): string {
  if (!unit) return '';
  const words: Readonly<Record<string, string>> = {
    usd_per_share: '$ / share',
    usd: '$',
    decimal: 'fraction (shown as %)',
    pct_points: 'percentage points',
  };
  return words[unit] ?? unit.replace(/_/g, ' ');
}

/** Catalogue lookup by field name. */
export function byName(catalogue: readonly CatalogueFeature[]): Map<string, CatalogueFeature> {
  return new Map(catalogue.map((f) => [f.name, f]));
}
