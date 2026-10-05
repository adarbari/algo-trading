/**
 * DataTable column model: the caller's `DataTableColumn` (label, description, accessor,
 * format, slot) mapped onto TanStack Table v9 column definitions, plus the CSS grid template
 * every row shares. TanStack stays an implementation detail: no TanStack type is public.
 */
import {
  columnVisibilityFeature,
  createColumnHelper,
  createSortedRowModel,
  rowSelectionFeature,
  rowSortingFeature,
  tableFeatures,
  type ColumnDef,
  type Row as TableRow,
  type RowData,
} from '@tanstack/react-table';
import type { ReactNode } from 'react';

import { isNumericFormat, type FormattedValue, type ValueFormat } from '../../format';

/** Column width steps (minimum widths; every column also shares leftover space). */
export type ColumnWidth = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl';

export interface DataTableCellContext<TRow> {
  row: TRow;
  /** The raw value from `value(row)`. */
  value: unknown;
  /** The value formatted with the column's `format` (text + up / down / muted tone). */
  formatted: FormattedValue;
}

export interface DataTableColumn<TRow> {
  /** Stable id: sort and visibility state refer to it. */
  id: string;
  /** Header text (also the column picker label). */
  header: string;
  /** What the column means: shown in the column picker and announced with the header. */
  description?: string;
  /** Reads the cell value from a row (also the sort key). */
  value: (row: TRow) => unknown;
  /** How the value reads (`percent`, `currency-compact`, `delta`, ...). Numeric formats right-align. */
  format?: ValueFormat;
  /** Cell alignment (default: `end` for numeric formats, otherwise `start`). */
  align?: 'start' | 'end';
  /** Slot: renders the cell instead of the formatted text (a badge, a ticker with its name). */
  cell?: (context: DataTableCellContext<TRow>) => ReactNode;
  /** Sortable (default true). */
  sortable?: boolean;
  /** Can be hidden from the column picker (default true). */
  hideable?: boolean;
  /** Minimum width step (default `sm` for numeric formats, `md` otherwise). */
  width?: ColumnWidth;
  /** Take three times the share of leftover width (the main text column). */
  grow?: boolean;
  /** Monospace text (symbols, ids). */
  mono?: boolean;
  /** Text colour of plain cells: `default`, `secondary` or `muted`. */
  tone?: 'default' | 'secondary' | 'muted';
  /** Tints a cell from its row (a criterion's near miss or miss); no tint when `undefined`. */
  fill?: (row: TRow) => DataTableFill | undefined;
}

/**
 * A tint behind a cell: `warning` (a near miss) or `down` (a miss). The cell's text still says
 * what it is (the value, or a "Why" column beside it), so colour never carries the meaning alone.
 */
export type DataTableFill = 'warning' | 'down';

/** The TanStack features the DataTable registers (module scope: stable across renders). */
export const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  columnVisibilityFeature,
  rowSelectionFeature,
});

type Features = typeof features;

export function alignOf<TRow>(column: DataTableColumn<TRow>): 'start' | 'end' {
  return column.align ?? (isNumericFormat(column.format) ? 'end' : 'start');
}

export function widthOf<TRow>(column: DataTableColumn<TRow>): ColumnWidth {
  return column.width ?? (isNumericFormat(column.format) ? 'sm' : 'md');
}

const missing = (value: unknown): boolean =>
  value === null || value === undefined || (typeof value === 'number' && Number.isNaN(value));

/** Ascending order for mixed values: numbers, dates, then text (natural order). */
export function compareValues(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (a instanceof Date && b instanceof Date) return a.getTime() - b.getTime();
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b);
  return String(a).localeCompare(String(b), 'en', { numeric: true, sensitivity: 'base' });
}

/** TanStack column definitions: missing values become `undefined` and always sort last. */
export function toColumnDefs<TRow extends RowData>(
  columns: readonly DataTableColumn<TRow>[],
): ColumnDef<Features, TRow>[] {
  const helper = createColumnHelper<Features, TRow>();
  return columns.map((column) =>
    helper.accessor(
      (row: TRow) => {
        const value = column.value(row);
        return missing(value) ? undefined : value;
      },
      {
        id: column.id,
        header: column.header,
        enableSorting: column.sortable ?? true,
        enableHiding: column.hideable ?? true,
        sortUndefined: 'last',
        sortFn: (rowA: TableRow<Features, TRow>, rowB: TableRow<Features, TRow>, id: string) =>
          compareValues(rowA.getValue(id), rowB.getValue(id)),
      },
    ),
  );
}

/** One grid track per visible column (and the selection column): every row uses the same template. */
export function gridTemplate<TRow>(columns: readonly DataTableColumn<TRow>[], selectable: boolean) {
  const tracks = columns.map(
    (column) => `minmax(var(--dt-w-${widthOf(column)}), ${column.grow ? 3 : 1}fr)`,
  );
  const mins = columns.map((column) => `var(--dt-w-${widthOf(column)})`);
  if (selectable) {
    tracks.unshift('var(--dt-w-select)');
    mins.unshift('var(--dt-w-select)');
  }
  return {
    template: tracks.join(' ') || 'minmax(0, 1fr)',
    minWidth: mins.length > 0 ? `calc(${mins.join(' + ')})` : '0',
  };
}
