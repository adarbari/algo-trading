/**
 * The filter model (ADR 0082): the server's definitions of a surface's filters, the counts it
 * serves with a filtered list (facets), and the conversion of the filters in force into the
 * `FilterInput` list a read takes. Pure: it renames served values; every count is the server's
 * (ADR 0038), nothing is computed here.
 */
import type { gqlTypes } from '@/shared/api';

export type FilterKind = gqlTypes.FilterKind;
export type FilterGroup = gqlTypes.FilterGroup;
export type FilterInput = gqlTypes.FilterInput;
export type FilterSetResponse = gqlTypes.FilterSetQuery;
export type FilterDefinition = NonNullable<FilterSetResponse['filterSet']>['filters'][number];

/** The counts of one filtered list, as the read serves them (`facets` of a list field). */
export interface FilterFacets {
  total: number;
  matched: number;
  items: readonly {
    id: string;
    active: boolean;
    removes?: number | null | undefined;
    unknown: number;
    options: readonly { value: string; count: number }[];
    bins: readonly { lo: number; hi: number; count: number }[];
  }[];
}

/** A filter in force, as the URL state holds it (structurally the filter bar's `FilterState`). */
export interface AppliedFilter {
  id: string;
  values?: readonly string[] | undefined;
  min?: number | undefined;
  max?: number | undefined;
  within?: { amount: number; unit: 'days' | 'sessions' } | undefined;
  active: boolean;
}

/** The groups in the order the bar lists them, with the button's name. */
export const FILTER_GROUPS: readonly { id: FilterGroup; label: string }[] = [
  { id: 'SETUP', label: 'Setup' },
  { id: 'CHANGED', label: 'What changed' },
  { id: 'TRADEABLE', label: 'Tradeable' },
  { id: 'COMING_UP', label: 'Coming up' },
  { id: 'MORE', label: 'More filters' },
];

/** The filters in force as a read's `filters` argument (null: none, so the read is the plain one). */
export function toFilterInputs(filters: readonly AppliedFilter[]): FilterInput[] | null {
  if (filters.length === 0) return null;
  return filters.map((f) => ({
    id: f.id,
    values: [...(f.values ?? [])],
    min: f.min ?? null,
    max: f.max ?? null,
    within: f.within
      ? { amount: f.within.amount, unit: f.within.unit === 'days' ? 'DAYS' : 'SESSIONS' }
      : null,
    active: f.active,
  }));
}
