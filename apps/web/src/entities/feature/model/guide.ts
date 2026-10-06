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
