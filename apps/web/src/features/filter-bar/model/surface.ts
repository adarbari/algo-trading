/**
 * What the surface filter bar shows for the filters in force, from the server's definitions and
 * facets (ADR 0082, 0038): the applied chips (label, value as text, rows each removes), the
 * zero-result recovery chips, the per-group counts and the count line. Pure; every number shown
 * is the server's, nothing is counted here.
 */
import { formatValue, type FilterChipItem, type RecoveryItem } from '@algotrade/ui';

import type { FilterDefinition, FilterFacets, FilterGroup } from '@/entities/filter';

import type { FilterState } from './state';

/** The most loosening chips a zero-result list offers. */
export const RECOVERY_LIMIT = 3;

const num = (n: number) => formatValue(n, { kind: 'number' }).text;

const byId = <T extends { id: string }>(items: readonly T[] | undefined) =>
  new Map((items ?? []).map((item) => [item.id, item]));

/**
 * The caller's name for a stored value of a filter (a screener's name for its id, a decision's
 * wording); undefined: none, and the definition's label is used.
 */
export type LabelOf = (filterId: string, value: string) => string | undefined;

/** A filter's value as the chip says it: option labels, a range's ends, a window's size. */
export function valueText(
  filter: FilterState,
  definition: FilterDefinition | undefined,
  labelOf?: LabelOf,
): string {
  if (filter.within) return `≤ ${num(filter.within.amount)} ${filter.within.unit}`;
  if (filter.min !== undefined || filter.max !== undefined) {
    const percent = definition?.unit === 'PERCENT';
    const n = (v: number) => (percent ? `${num(Number((v * 100).toPrecision(12)))}%` : num(v));
    if (filter.min !== undefined && filter.max !== undefined) {
      return `${n(filter.min)}–${n(filter.max)}`;
    }
    return filter.min !== undefined ? `≥ ${n(filter.min)}` : `≤ ${n(filter.max ?? 0)}`;
  }
  const labels = new Map((definition?.options ?? []).map((o) => [o.value, o.label]));
  return (filter.values ?? []).map((v) => labelOf?.(filter.id, v) ?? labels.get(v) ?? v).join(', ');
}

/** One chip per filter in force, in the URL's order (an id the surface no longer defines keeps its id as its name). */
export function chipItems(
  filters: readonly FilterState[],
  definitions: readonly FilterDefinition[],
  facets: FilterFacets | null | undefined,
  labelOf?: LabelOf,
): FilterChipItem[] {
  const defined = byId(definitions);
  const counted = byId(facets?.items);
  return filters.map((filter) => {
    const facet = counted.get(filter.id);
    return {
      id: filter.id,
      label: defined.get(filter.id)?.label ?? filter.id,
      valueText: valueText(filter, defined.get(filter.id), labelOf),
      active: filter.active,
      ...(facet?.removes != null && { removes: facet.removes }),
      ...(facet && { unknown: facet.unknown }),
    };
  });
}

/**
 * The best ways back from an empty list: the filters in force with the most rows they remove (with
 * nothing matching, the rows the list would show without them), largest first.
 */
export function recoveryItems(
  filters: readonly FilterState[],
  definitions: readonly FilterDefinition[],
  facets: FilterFacets | null | undefined,
): RecoveryItem[] {
  const defined = byId(definitions);
  const counted = byId(facets?.items);
  return filters
    .filter((f) => f.active)
    .flatMap((f) => {
      const removes = counted.get(f.id)?.removes ?? 0;
      return removes > 0
        ? [{ id: f.id, label: defined.get(f.id)?.label ?? f.id, gives: removes }]
        : [];
    })
    .sort((a, b) => b.gives - a.gives)
    .slice(0, RECOVERY_LIMIT);
}

/** How many filters in force each group holds. */
export function groupCounts(
  filters: readonly FilterState[],
  definitions: readonly FilterDefinition[],
): Map<FilterGroup, number> {
  const defined = byId(definitions);
  const counts = new Map<FilterGroup, number>();
  for (const filter of filters) {
    const group = defined.get(filter.id)?.group;
    if (group) counts.set(group, (counts.get(group) ?? 0) + 1);
  }
  return counts;
}

/** "12 of 340". */
export function countLine(facets: FilterFacets | null | undefined): string | undefined {
  return facets ? `${num(facets.matched)} of ${num(facets.total)}` : undefined;
}
