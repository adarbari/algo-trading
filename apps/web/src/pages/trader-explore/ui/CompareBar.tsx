/**
 * Explore's compare bar: the compare set as removable chips, the focused one marked; a chip
 * focuses its ticker. The page shows it at the top of the detail (wide) or above the ticker
 * table (narrow, where the detail is a sheet).
 */
import { CompareSetBar } from '@/features/compare-set';

import type { ExploreSearch } from '@/entities/explore';
import { exploreState, type SearchPatch } from '../model/state';

export interface CompareBarProps {
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
}

export function CompareBar({ search, onSearchChange }: CompareBarProps) {
  const { selected, focused } = exploreState(search);
  const setSelected = (next: readonly string[]) => {
    onSearchChange({
      sel: next.length > 0 ? next.join(',') : undefined,
      focus: focused && next.includes(focused) ? search.focus : undefined,
    });
  };
  const focus = (symbol: string) => {
    onSearchChange({ focus: symbol, expiry: undefined, feature: undefined });
  };
  return (
    <CompareSetBar
      symbols={selected}
      focused={focused}
      onRemove={(symbol) => {
        setSelected(selected.filter((s) => s !== symbol));
      }}
      onClear={() => {
        setSelected([]);
      }}
      onFocus={focus}
      onOpen={focus}
    />
  );
}
