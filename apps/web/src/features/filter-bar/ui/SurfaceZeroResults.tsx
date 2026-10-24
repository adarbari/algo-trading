/**
 * What a filtered list shows when nothing matches: "No <things> match all K filters" and the best
 * ways back, "Switch off X gives N" per filter (the server's `removes`), then Clear all. Put it
 * where the table's empty message goes.
 */
import { ZeroResults } from '@algotrade/ui';

import { useFilterSet, type FilterFacets } from '@/entities/filter';

import type { FilterStateApi } from '../api/use-filter-state';
import { recoveryItems } from '../model/surface';

export interface SurfaceZeroResultsProps {
  surface: string;
  state: FilterStateApi;
  facets: FilterFacets | null | undefined;
}

export function SurfaceZeroResults({ surface, state, facets }: SurfaceZeroResultsProps) {
  const set = useFilterSet(surface);
  const definitions = set.data?.filterSet?.filters ?? [];
  const noun = (set.data?.filterSet?.label ?? '').toLowerCase();
  if (!set.data?.filterSet) return null;
  const inForce = state.filters.filter((f) => f.active).length;
  return (
    <ZeroResults
      title={
        inForce === 1
          ? `No ${noun} match this filter`
          : `No ${noun} match all ${String(inForce)} filters`
      }
      items={recoveryItems(state.filters, definitions, facets).map((item) => ({
        ...item,
        label: `Switch off ${item.label}`,
      }))}
      onPick={state.toggle}
      onClearAll={state.clear}
    />
  );
}
