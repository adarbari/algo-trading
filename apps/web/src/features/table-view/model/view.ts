/**
 * A saved view of a table as the page holds it: the catalogue columns added, the sort and the
 * decisions shown; a table's sort to and from its saved text (`-` prefix: descending; the
 * table's default sort is saved as none); and a screener's scope. Pure.
 */
import type { DataTableSort } from '@algotrade/ui';

export interface ViewContent {
  columns: readonly string[];
  /** The table column ids the user added back on a narrow (phone) table. */
  narrowColumns: readonly string[];
  /** A column id, `-` prefix for descending; null: the table's default. */
  sort: string | null;
  decisions: readonly string[];
}

/** The scope of a screener's results (`screener:<id>`, as `preferences.toml` keys it). */
export function screenerScope(id: string): string {
  return `screener:${id}`;
}

/** `-criterion:iv30` -> the table's sort; none (or blank) -> `fallback`. */
export function parseSort(
  value: string | null | undefined,
  fallback: DataTableSort,
): DataTableSort {
  if (!value) return fallback;
  return value.startsWith('-')
    ? { columnId: value.slice(1), direction: 'desc' }
    : { columnId: value, direction: 'asc' };
}

/** The table's sort as saved: null for none, or for the table's own default. */
export function formatSort(
  sort: DataTableSort | null,
  fallback: DataTableSort | null = null,
): string | null {
  if (sort === null) return null;
  if (fallback && sort.columnId === fallback.columnId && sort.direction === fallback.direction) {
    return null;
  }
  return `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}`;
}
