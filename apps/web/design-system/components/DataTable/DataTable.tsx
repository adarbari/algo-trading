/**
 * DataTable: the generic data grid (screener results, ticker lists, quality checks). Typed
 * columns (header, description, accessor, format, cell slot); single-column sorting with
 * `aria-sort`; numbers right-aligned in tabular figures through the shared formatters (number,
 * percent, `$13.99B`, date, signed delta with up / down tone); a column picker fed by the
 * caller's columns and descriptions; controlled row selection (checkbox column, Shift-click
 * ranges); a sticky header; virtual scrolling with fixed row heights per density (tens of
 * thousands of rows); loading / empty / error states; keyboard navigation (arrows, Page Up /
 * Down, Home / End move the active row, Enter activates it, Space selects it); horizontal
 * scrolling on narrow widths. Built on TanStack Table + Virtual, which stay internal.
 */
import {
  useTable,
  type RowData,
  type RowSelectionState,
  type SortingState,
  type Updater,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';

import { formatValue } from '../../format';
import { Checkbox } from '../Checkbox';
import { ColumnPicker } from './ColumnPicker';
import { alignOf, features, gridTemplate, toColumnDefs, type DataTableColumn } from './columns';
import styles from './DataTable.module.css';
import { useRowHeight } from './useRowHeight';

export interface DataTableSort {
  columnId: string;
  direction: 'asc' | 'desc';
}

export interface DataTableProps<TRow> {
  /** Column definitions, in display order. */
  columns: readonly DataTableColumn<TRow>[];
  rows: readonly TRow[];
  /** Stable id of a row (selection and focus follow it through sorting). */
  getRowId: (row: TRow) => string;
  /** Accessible name of the grid, e.g. "Preview results". */
  label: string;
  /** Short name of a row for its checkbox ("Select AAPL"); default the row id. */
  getRowLabel?: (row: TRow) => string;
  /** Controlled sort (pair with `onSortChange`); `null` = unsorted (input order). */
  sort?: DataTableSort | null;
  /** Initial sort when uncontrolled. */
  defaultSort?: DataTableSort | null;
  onSortChange?: (sort: DataTableSort | null) => void;
  /** Controlled hidden column ids (pair with `onHiddenColumnsChange`). */
  hiddenColumns?: readonly string[];
  /** Initially hidden column ids when uncontrolled. */
  defaultHiddenColumns?: readonly string[];
  onHiddenColumnsChange?: (hidden: string[]) => void;
  /** Show the "Columns" picker in the toolbar. */
  columnPicker?: boolean;
  /** Add the checkbox column. Selection is controlled: pass `selectedIds` and `onSelectionChange`. */
  selectable?: boolean;
  selectedIds?: readonly string[];
  onSelectionChange?: (ids: string[]) => void;
  /** Enter on the active row, or a click on a row. */
  onRowActivate?: (row: TRow) => void;
  /** `ready` (default), `loading` (placeholder rows) or `error` (shows `errorMessage`). */
  status?: 'ready' | 'loading' | 'error';
  errorMessage?: ReactNode;
  /** Shown when there are no rows. */
  emptyMessage?: ReactNode;
  /** Height of the scrolling body in rows (default 12); fewer rows shrink the table. */
  visibleRows?: number;
  /** Lines of text per row: 1 (default) or 2 (a symbol with its name underneath). */
  rowLines?: 1 | 2;
  /** Toolbar content before the column picker (a count, filters). */
  toolbar?: ReactNode;
}

const EMPTY_IDS: readonly string[] = [];
const LOADING_ROWS = 6;

const toSorting = (sort: DataTableSort | null | undefined): SortingState =>
  sort ? [{ id: sort.columnId, desc: sort.direction === 'desc' }] : [];

const resolve = <T,>(updater: Updater<T>, previous: T): T =>
  typeof updater === 'function' ? (updater as (old: T) => T)(previous) : updater;

export function DataTable<TRow extends RowData>({
  columns,
  rows,
  getRowId,
  label,
  getRowLabel,
  sort,
  defaultSort = null,
  onSortChange,
  hiddenColumns,
  defaultHiddenColumns = EMPTY_IDS,
  onHiddenColumnsChange,
  columnPicker = false,
  selectable = false,
  selectedIds = EMPTY_IDS,
  onSelectionChange,
  onRowActivate,
  status = 'ready',
  errorMessage = 'The data failed to load.',
  emptyMessage = 'No rows to show',
  visibleRows = 12,
  rowLines = 1,
  toolbar,
}: DataTableProps<TRow>) {
  const id = useId();
  const scrollRef = useRef<HTMLDivElement>(null);
  const { base: baseHeight, row: rowHeight } = useRowHeight(scrollRef, rowLines);

  // Sort and hidden columns: controlled when the prop is given, otherwise owned here.
  const [ownSort, setOwnSort] = useState<DataTableSort | null>(defaultSort);
  const [ownHidden, setOwnHidden] = useState<readonly string[]>(defaultHiddenColumns);
  const activeSort = sort === undefined ? ownSort : sort;
  const hidden = hiddenColumns ?? ownHidden;

  const setSort = (next: DataTableSort | null) => {
    if (sort === undefined) setOwnSort(next);
    onSortChange?.(next);
  };
  const setHidden = (next: string[]) => {
    if (hiddenColumns === undefined) setOwnHidden(next);
    onHiddenColumnsChange?.(next);
  };

  const columnDefs = useMemo(() => toColumnDefs(columns), [columns]);
  const data = rows as TRow[];
  const sorting = useMemo(() => toSorting(activeSort), [activeSort]);
  const columnVisibility = useMemo(
    () => Object.fromEntries(hidden.map((columnId) => [columnId, false])),
    [hidden],
  );
  const rowSelection = useMemo<RowSelectionState>(
    () => Object.fromEntries(selectedIds.map((rowId) => [rowId, true])),
    [selectedIds],
  );

  const table = useTable({
    features,
    columns: columnDefs,
    data,
    getRowId: (row: TRow) => getRowId(row),
    state: { sorting, columnVisibility, rowSelection },
    onSortingChange: (updater: Updater<SortingState>) => {
      const next = resolve(updater, sorting)[0];
      setSort(next ? { columnId: next.id, direction: next.desc ? 'desc' : 'asc' } : null);
    },
    onColumnVisibilityChange: (updater: Updater<Record<string, boolean>>) => {
      const next = resolve(updater, columnVisibility);
      setHidden(Object.keys(next).filter((columnId) => next[columnId] === false));
    },
    onRowSelectionChange: (updater: Updater<RowSelectionState>) => {
      const next = resolve(updater, rowSelection);
      onSelectionChange?.(Object.keys(next).filter((rowId) => next[rowId]));
    },
    enableRowSelection: selectable,
    enableSortingRemoval: false,
  });

  const visibleColumns = columns.filter((column) => columnVisibility[column.id] !== false);
  const tableRows = table.getRowModel().rows;
  const ready = status === 'ready';
  const bodyRows = ready ? tableRows.length : 0;

  // TanStack Virtual returns fresh functions each render; the compiler skips memoizing here.
  // eslint-disable-next-line react-hooks/incompatible-library -- the virtualizer re-renders by design
  const virtualizer = useVirtualizer({
    count: bodyRows,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    getItemKey: (index) => tableRows[index]?.id ?? index,
    overscan: 8,
    scrollMargin: baseHeight,
    scrollPaddingStart: baseHeight,
    initialRect: { width: 0, height: rowHeight * visibleRows },
  });

  // Density changed: every row's fixed height changed with it.
  useLayoutEffect(() => {
    virtualizer.measure();
  }, [virtualizer, rowHeight]);

  // The active (keyboard) row, by id so it survives sorting.
  const [activeId, setActiveId] = useState<string | null>(null);
  const activeIndex = activeId === null ? -1 : tableRows.findIndex((row) => row.id === activeId);

  function moveTo(index: number) {
    if (bodyRows === 0) return;
    const next = Math.min(Math.max(index, 0), bodyRows - 1);
    const row = tableRows[next];
    if (!row) return;
    setActiveId(row.id);
    virtualizer.scrollToIndex(next, { align: 'auto' });
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget || bodyRows === 0) return;
    const at = activeIndex < 0 ? -1 : activeIndex;
    const page = Math.max(1, visibleRows - 1);
    const targets: Record<string, number | undefined> = {
      ArrowDown: at + 1,
      ArrowUp: Math.max(at - 1, 0),
      PageDown: at + page,
      PageUp: Math.max(at - page, 0),
      Home: 0,
      End: bodyRows - 1,
    };
    const target = targets[event.key];
    if (target !== undefined) {
      event.preventDefault();
      moveTo(target);
      return;
    }
    const row = tableRows[at];
    if (!row) return;
    if (event.key === 'Enter' && onRowActivate) {
      event.preventDefault();
      onRowActivate(row.original);
    } else if (event.key === ' ' && selectable) {
      event.preventDefault();
      row.toggleSelected();
    }
  }

  /** A click on a row (delegated: rows are reached by keyboard through the grid) activates it. */
  function onClick(event: MouseEvent<HTMLDivElement>) {
    const target = event.target as Element;
    if (target.closest('input, label, button, a')) return;
    const rowId = target.closest<HTMLElement>('[data-row-id]')?.dataset['rowId'];
    const row = rowId === undefined ? undefined : tableRows.find((r) => r.id === rowId);
    if (!row) return;
    setActiveId(row.id);
    onRowActivate?.(row.original);
  }

  const { template, minWidth } = gridTemplate(visibleColumns, selectable);
  const gridVars = {
    '--dt-columns': template,
    '--dt-min-width': minWidth,
    '--dt-visible-rows': visibleRows,
    '--dt-row-lines': rowLines,
  } as CSSProperties;

  const allSelected = table.getIsAllRowsSelected();
  const someSelected = table.getIsSomeRowsSelected();
  const rowIdFor = (rowId: string) => `${id}-row-${encodeURIComponent(rowId)}`;
  const activeVisible =
    activeIndex >= 0 && virtualizer.getVirtualItems().some((item) => item.index === activeIndex);
  const colCount = visibleColumns.length + (selectable ? 1 : 0);

  const pickerColumns = columns.map((column) => ({
    id: column.id,
    header: column.header,
    ...(column.description === undefined ? {} : { description: column.description }),
    visible: columnVisibility[column.id] !== false,
    hideable: column.hideable ?? true,
  }));

  function stateRow(content: ReactNode, alert = false) {
    return (
      <div className={styles.stateRow} role="row" aria-rowindex={2}>
        <div
          className={styles.stateCell}
          role="gridcell"
          aria-colspan={colCount}
          data-alert={alert || undefined}
        >
          {alert ? <span role="alert">{content}</span> : content}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.root} style={gridVars}>
      {(toolbar !== undefined || columnPicker) && (
        <div className={styles.toolbar}>
          <div className={styles.toolbarStart}>{toolbar}</div>
          {columnPicker && (
            <ColumnPicker
              columns={pickerColumns}
              onToggle={(columnId, visible) => {
                setHidden(visible ? hidden.filter((h) => h !== columnId) : [...hidden, columnId]);
              }}
            />
          )}
        </div>
      )}
      <div
        ref={scrollRef}
        className={styles.scroller}
        role="grid"
        aria-label={label}
        aria-rowcount={ready ? bodyRows + 1 : -1}
        aria-colcount={colCount}
        aria-multiselectable={selectable || undefined}
        aria-busy={status === 'loading' || undefined}
        aria-activedescendant={activeVisible && activeId !== null ? rowIdFor(activeId) : undefined}
        tabIndex={0}
        data-lines={rowLines}
        onKeyDown={onKeyDown}
        onClick={onClick}
        onFocus={(event) => {
          if (event.target === event.currentTarget && activeIndex < 0 && bodyRows > 0) moveTo(0);
        }}
      >
        <div className={styles.canvas}>
          <div className={styles.header} role="rowgroup">
            {table.getHeaderGroups().map((group) => (
              <div key={group.id} className={styles.row} role="row" aria-rowindex={1}>
                {selectable && (
                  <div className={styles.selectCell} role="columnheader">
                    <Checkbox
                      label="Select all rows"
                      hideLabel
                      checked={allSelected}
                      indeterminate={someSelected && !allSelected}
                      disabled={!ready || bodyRows === 0}
                      onCheckedChange={() => {
                        table.toggleAllRowsSelected(!allSelected);
                      }}
                    />
                  </div>
                )}
                {group.headers.map((header) => {
                  const column = columns.find((c) => c.id === header.column.id);
                  if (!column) return null;
                  const sorted = header.column.getIsSorted();
                  const canSort = header.column.getCanSort();
                  const align = alignOf(column);
                  const descriptionId = column.description ? `${id}-desc-${column.id}` : undefined;
                  return (
                    <div
                      key={header.id}
                      className={styles.headerCell}
                      role="columnheader"
                      data-align={align}
                      aria-sort={
                        canSort
                          ? sorted === 'asc'
                            ? 'ascending'
                            : sorted === 'desc'
                              ? 'descending'
                              : 'none'
                          : undefined
                      }
                      title={column.description}
                    >
                      {canSort ? (
                        <button
                          type="button"
                          className={styles.sortButton}
                          data-sorted={sorted || undefined}
                          aria-describedby={descriptionId}
                          onClick={() => {
                            // Numbers sort high-first on the first click, text A-Z.
                            const first = align === 'end' ? 'desc' : 'asc';
                            const direction = sorted ? (sorted === 'asc' ? 'desc' : 'asc') : first;
                            setSort({ columnId: column.id, direction });
                          }}
                        >
                          <span className={styles.headerText}>{column.header}</span>
                          <svg
                            className={styles.sortIcon}
                            viewBox="0 0 8 10"
                            aria-hidden="true"
                            focusable="false"
                          >
                            <path data-part="up" d="M4 1 7 4H1z" />
                            <path data-part="down" d="M4 9 1 6h6z" />
                          </svg>
                        </button>
                      ) : (
                        <span className={styles.headerText}>{column.header}</span>
                      )}
                      {descriptionId && (
                        <span id={descriptionId} className={styles.hidden}>
                          {column.description}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
          <div
            className={styles.body}
            role="rowgroup"
            style={ready && bodyRows > 0 ? { height: virtualizer.getTotalSize() } : undefined}
          >
            {status === 'loading' &&
              Array.from({ length: LOADING_ROWS }, (_, index) => (
                <div
                  key={index}
                  className={styles.row}
                  role="row"
                  aria-rowindex={index + 2}
                  data-placeholder
                >
                  {Array.from({ length: colCount }, (__, cell) => (
                    <div key={cell} className={styles.cell} role="gridcell">
                      <span className={styles.placeholder} aria-hidden="true" />
                    </div>
                  ))}
                </div>
              ))}
            {status === 'error' && stateRow(errorMessage, true)}
            {ready && bodyRows === 0 && stateRow(emptyMessage)}
            {ready &&
              virtualizer.getVirtualItems().map((item) => {
                const row = tableRows[item.index];
                if (!row) return null;
                const selected = row.getIsSelected();
                return (
                  <div
                    key={row.id}
                    id={rowIdFor(row.id)}
                    className={styles.row}
                    role="row"
                    aria-rowindex={item.index + 2}
                    aria-selected={selectable ? selected : undefined}
                    data-active={item.index === activeIndex || undefined}
                    data-virtual
                    style={{
                      transform: `translateY(${item.start - virtualizer.options.scrollMargin}px)`,
                    }}
                    data-row-id={row.id}
                  >
                    {selectable && (
                      <div className={styles.selectCell} role="gridcell">
                        <Checkbox
                          label={`Select ${getRowLabel ? getRowLabel(row.original) : row.id}`}
                          hideLabel
                          checked={selected}
                          excludeFromTabOrder
                          onCheckedChange={(_checked, event) => {
                            row.getToggleSelectedHandler()(event);
                          }}
                        />
                      </div>
                    )}
                    {visibleColumns.map((column) => {
                      const value = row.getValue(column.id);
                      const formatted = formatValue(value, column.format);
                      return (
                        <div
                          key={column.id}
                          className={styles.cell}
                          role="gridcell"
                          data-align={alignOf(column)}
                          data-mono={column.mono || undefined}
                          data-fill={column.fill?.(row.original)}
                          data-tone={
                            column.cell
                              ? undefined
                              : formatted.tone !== 'default'
                                ? formatted.tone
                                : column.tone
                          }
                        >
                          {column.cell ? (
                            column.cell({ row: row.original, value, formatted })
                          ) : (
                            <span className={styles.cellText}>{formatted.text}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
          </div>
        </div>
      </div>
    </div>
  );
}
