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
  /** The filter bar's `f` string (ADR 0082); empty: none. */
  filters: string;
}

/** An `f` string cut into its entries and each entry's filter id (`!` and escapes undone). */
function entries(f: string): { id: string; entry: string }[] {
  return f
    .split(';')
    .filter((entry) => entry.includes(':'))
    .map((entry) => {
      const head = entry.slice(0, entry.indexOf(':')).replace(/^!/, '');
      let id = head;
      try {
        id = decodeURIComponent(head);
      } catch {
        // an undecodable id is kept as written; no definition will name it
      }
      return { id, entry };
    });
}

/**
 * The saved `f` as the surface can use it: entries of filters the surface still defines are
 * kept, the rest dropped and their ids reported (a view survives a definition change; the
 * page says what it dropped). `known` undefined: the definitions are not known, nothing dropped.
 */
export function restorableFilters(
  f: string,
  known: readonly string[] | undefined,
): { f: string; dropped: string[] } {
  if (known === undefined) return { f, dropped: [] };
  const kept = entries(f).filter(({ id }) => known.includes(id));
  const dropped = entries(f)
    .filter(({ id }) => !known.includes(id))
    .map(({ id }) => id);
  return { f: kept.map(({ entry }) => entry).join(';'), dropped };
}

/** The scope of a screener's results (`screener:<id>`, as `preferences.toml` keys it). */
export function screenerScope(id: string): string {
  return `screener:${id}`;
}

/** The scope of a list with a filter bar (`surface:<name>`, its filters file's name). */
export function surfaceScope(name: string): string {
  return `surface:${name}`;
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
