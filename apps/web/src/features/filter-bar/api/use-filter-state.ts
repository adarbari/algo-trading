/**
 * The filter list as React state over the `f` search parameter. The router is touched only in
 * `src/app` (ADR 0025 rule 4), so the route hands the current `f` and a setter that navigates
 * with `replace` (like the Ideas route's `onSearchChange`); this hook decodes, patches and
 * writes back.
 */
import { useCallback, useMemo } from 'react';

import { decodeFilters, encodeFilters } from '../model/codec';
import type { FilterPatch, FilterState } from '../model/state';

export interface FilterStateApi {
  filters: FilterState[];
  /** Change one filter, adding it (on) when absent; setting a kind of value clears the others. */
  set: (id: string, patch: FilterPatch) => void;
  /** Switch a filter off or back on (kept either way). */
  toggle: (id: string) => void;
  remove: (id: string) => void;
  clear: () => void;
}

const KINDS = ['values', 'min', 'max', 'within'] as const;
type Kind = (typeof KINDS)[number];
const KIND_OF: Record<Kind, 'pick' | 'range' | 'window'> = {
  values: 'pick',
  min: 'range',
  max: 'range',
  within: 'window',
};

function merged(previous: FilterState | undefined, id: string, patch: FilterPatch): FilterState {
  const touched = new Set(KINDS.filter((k) => patch[k] !== undefined).map((k) => KIND_OF[k]));
  // Setting one kind of value drops the others the filter held.
  const kept = Object.entries({ ...previous }).filter(
    ([key]) => !(key in KIND_OF) || touched.size === 0 || touched.has(KIND_OF[key as Kind]),
  );
  // The patch wins key by key, an `undefined` in it removes the key (an emptied end of a range).
  const next = Object.fromEntries(
    Object.entries({ ...Object.fromEntries(kept), ...patch }).filter(([, v]) => v !== undefined),
  );
  return { active: true, ...next, id };
}

/** `f` is the route's current search value; `onChange` writes the next one (undefined: none). */
export function useFilterState(
  f: string | undefined,
  onChange: (next: string | undefined) => void,
): FilterStateApi {
  const filters = useMemo(() => decodeFilters(f), [f]);
  const write = useCallback(
    (next: readonly FilterState[]) => {
      onChange(encodeFilters(next) || undefined);
    },
    [onChange],
  );
  return useMemo(
    () => ({
      filters,
      set: (id, patch) => {
        const exists = filters.some((x) => x.id === id);
        write(
          exists
            ? filters.map((x) => (x.id === id ? merged(x, id, patch) : x))
            : [...filters, merged(undefined, id, patch)],
        );
      },
      toggle: (id) => {
        write(filters.map((x) => (x.id === id ? { ...x, active: !x.active } : x)));
      },
      remove: (id) => {
        write(filters.filter((x) => x.id !== id));
      },
      clear: () => {
        write([]);
      },
    }),
    [filters, write],
  );
}
