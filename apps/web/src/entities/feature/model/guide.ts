/**
 * The site field guide's entry of a catalogue field as `Query.catalogue` serves it (ADR 0041
 * amended): how to read the field, the criterion per intent (as a rule screen takes it), the
 * caveats and sources. Pure readers of a use's JSON parts (its value, its tolerance).
 */
import type { CatalogueFeature } from './catalogue';

export type FieldGuide = NonNullable<CatalogueFeature['guide']>;
export type GuideUse = FieldGuide['uses'][number];

/** A use's tolerance: a number in the field's unit, or a share of the threshold; undefined for none. */
export function guideTolerance(use: GuideUse): number | { relative: number } | undefined {
  const raw: unknown = use.tolerance;
  if (typeof raw === 'number') return raw;
  if (raw && typeof raw === 'object' && 'relative' in raw) {
    const relative = raw.relative;
    if (typeof relative === 'number') return { relative };
  }
  return undefined;
}

/** A use's value(s) as a list: two for `between`, each of `in` / `not_in`, one otherwise, none for `is_null` / `not_null`. */
export function guideValues(use: GuideUse): unknown[] {
  const raw: unknown = use.value;
  if (raw === null || raw === undefined) return [];
  return Array.isArray(raw) ? raw : [raw];
}

const NUMERIC_BANDS = new Set(['gt', 'gte', 'lt', 'lte', 'between']);

/** The criterion as the Builder writes it: `lte 0.10 soft tolerance 0.05` (`between 2 10`, `in A B`). */
export function ruleText(use: GuideUse): string {
  const parts = [use.op, ...guideValues(use).map(String), use.mode];
  const tolerance = guideTolerance(use);
  if (typeof tolerance === 'number') parts.push(`tolerance ${String(tolerance)}`);
  else if (tolerance) parts.push(`tolerance ${String(tolerance.relative * 100)}% of the threshold`);
  return parts.join(' ');
}

/** The span of values a numeric criterion passes, as a chart's value band (an absent edge is open); null for any other. */
export function bandOf(use: GuideUse): { from?: number; to?: number } | null {
  if (!NUMERIC_BANDS.has(use.op)) return null;
  const numbers = guideValues(use).filter((v): v is number => typeof v === 'number');
  const [first, second] = numbers;
  if (first === undefined) return null;
  if (use.op === 'between') return second === undefined ? null : { from: first, to: second };
  return use.op === 'gt' || use.op === 'gte' ? { from: first } : { to: first };
}
