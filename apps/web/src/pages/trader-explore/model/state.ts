/** Explore's typed state read from the search params, with the defaults filled in. */
import type { ChartRange, DataTableSort } from '@algotrade/ui';

import {
  DEFAULT_COLUMNS,
  DEFAULT_DIMENSIONS,
  parseSort,
  splitList,
  type ExploreSearch,
  type ExploreTab,
} from '@/entities/explore';

/** A change to the search params; `undefined` removes a key. */
export type SearchPatch = { [K in keyof ExploreSearch]?: ExploreSearch[K] | undefined };

/** One ticker opens on its overview; a compare set of two or more opens on the comparison. */
export function defaultTab(selectedCount: number): ExploreTab {
  return selectedCount > 1 ? 'compare' : 'overview';
}

export interface ExploreState {
  selected: string[];
  focused: string | null;
  tab: ExploreTab;
  columns: readonly string[];
  /** Columns added back on a narrow table (none by default). */
  narrowColumns: readonly string[];
  dimensions: readonly string[];
  sort: DataTableSort | null;
  range: ChartRange;
}

export function exploreState(search: ExploreSearch): ExploreState {
  const selected = splitList(search.sel);
  return {
    selected,
    focused: search.focus ?? selected[0] ?? null,
    tab: search.tab ?? defaultTab(selected.length),
    columns: search.cols === undefined ? DEFAULT_COLUMNS : splitList(search.cols),
    narrowColumns: splitList(search.ncols),
    dimensions: search.dims === undefined ? DEFAULT_DIMENSIONS : splitList(search.dims),
    sort: parseSort(search.sort),
    range: search.range ?? '1Y',
  };
}
