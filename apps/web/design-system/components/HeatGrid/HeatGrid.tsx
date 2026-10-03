/**
 * HeatGrid: a rows x columns grid of status cells, e.g. ingestion completeness (datasets x
 * sessions). Each cell is complete / partial / failed / not collected, with optional value text
 * (`99.7`); a header row names the columns, a header column names the rows, and a Legend
 * explains the colours. One cell can be selected (accent outline) to drill in. An ARIA grid:
 * arrow keys move between cells, Home / End to the row ends, Ctrl+Home / Ctrl+End to the
 * corners, Enter or Space (or a click) selects; only one cell is in the Tab order.
 */
import { useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';

import { type DataTone, Legend, toneStyles } from '../Legend';
import styles from './HeatGrid.module.css';

export type HeatStatus = 'complete' | 'partial' | 'failed' | 'not-collected';

export interface HeatGridCell {
  status: HeatStatus;
  /** Short value shown in the cell (e.g. completeness `99.7`). */
  text?: string;
}

export interface HeatGridColumn {
  id: string;
  label: string;
}

export interface HeatGridRow {
  id: string;
  label: string;
  /** Cells by column id; a missing cell is `not-collected`. */
  cells: Readonly<Record<string, HeatGridCell | undefined>>;
}

export interface HeatGridPosition {
  row: string;
  column: string;
}

export interface HeatGridProps {
  rows: readonly HeatGridRow[];
  columns: readonly HeatGridColumn[];
  /** Accessible name of the grid, e.g. "Completeness by dataset and session". */
  label: string;
  /** Header of the row-label column (visually hidden), e.g. "Dataset". */
  rowHeader?: string;
  /** The selected cell (controlled), outlined in the accent. */
  selected?: HeatGridPosition | null;
  /** Called when a cell is clicked or chosen with Enter / Space. */
  onSelect?: (position: HeatGridPosition) => void;
  /** Words for each status in the legend and the cells' accessible names. */
  statusLabels?: Partial<Record<HeatStatus, string>>;
  /** Show the status legend above the grid (default true). */
  legend?: boolean;
  loading?: boolean;
  /** Replaces the grid with this message. */
  error?: ReactNode;
  emptyMessage?: ReactNode;
}

const TONE: Record<HeatStatus, DataTone> = {
  complete: 'positive',
  partial: 'warning',
  failed: 'negative',
  'not-collected': 'empty',
};

const DEFAULT_LABELS: Record<HeatStatus, string> = {
  complete: 'complete',
  partial: 'partial',
  failed: 'failed',
  'not-collected': 'not collected',
};

const STATUSES: HeatStatus[] = ['complete', 'partial', 'failed', 'not-collected'];
const MISSING: HeatGridCell = { status: 'not-collected' };

export function HeatGrid({
  rows,
  columns,
  label,
  rowHeader = 'Row',
  selected = null,
  onSelect,
  statusLabels,
  legend = true,
  loading = false,
  error,
  emptyMessage = 'No data',
}: HeatGridProps) {
  const words = { ...DEFAULT_LABELS, ...statusLabels };
  const [focus, setFocus] = useState<{ r: number; c: number } | null>(null);
  const cellRefs = useRef(new Map<string, HTMLDivElement>());

  if (error !== undefined && error !== null && error !== false) {
    return (
      <p className={styles.message} data-tone="negative" role="alert">
        {error}
      </p>
    );
  }
  if (!loading && (rows.length === 0 || columns.length === 0)) {
    return <p className={styles.message}>{emptyMessage}</p>;
  }

  const selectedAt = selected
    ? {
        r: rows.findIndex((row) => row.id === selected.row),
        c: columns.findIndex((col) => col.id === selected.column),
      }
    : null;
  const inGrid = (p: { r: number; c: number } | null): p is { r: number; c: number } =>
    p !== null && p.r >= 0 && p.c >= 0 && p.r < rows.length && p.c < columns.length;
  const active = inGrid(focus) ? focus : inGrid(selectedAt) ? selectedAt : { r: 0, c: 0 };
  const key = (r: number, c: number) => `${r}:${c}`;

  function moveTo(r: number, c: number) {
    const next = {
      r: Math.min(Math.max(r, 0), rows.length - 1),
      c: Math.min(Math.max(c, 0), columns.length - 1),
    };
    setFocus(next);
    cellRefs.current.get(key(next.r, next.c))?.focus();
  }

  function choose(r: number, c: number) {
    const row = rows[r];
    const column = columns[c];
    if (row && column) onSelect?.({ row: row.id, column: column.id });
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>, r: number, c: number) {
    const last = { r: rows.length - 1, c: columns.length - 1 };
    const moves: Record<string, [number, number] | undefined> = {
      ArrowRight: [r, c + 1],
      ArrowLeft: [r, c - 1],
      ArrowDown: [r + 1, c],
      ArrowUp: [r - 1, c],
      Home: event.ctrlKey ? [0, 0] : [r, 0],
      End: event.ctrlKey ? [last.r, last.c] : [r, last.c],
    };
    const target = moves[event.key];
    if (target) {
      event.preventDefault();
      moveTo(target[0], target[1]);
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      choose(r, c);
    }
  }

  const gridVars = { '--heat-columns': Math.max(columns.length, 1) } as CSSProperties;
  return (
    <div className={styles.root}>
      {legend && (
        <Legend
          label="Status key"
          swatch="cell"
          items={STATUSES.map((status) => ({
            id: status,
            label: words[status],
            tone: TONE[status],
          }))}
        />
      )}
      <div className={styles.scroller}>
        <div
          className={styles.grid}
          role="grid"
          aria-label={label}
          aria-rowcount={rows.length + 1}
          aria-colcount={columns.length + 1}
          aria-busy={loading || undefined}
          style={gridVars}
        >
          <div className={styles.row} role="row" aria-rowindex={1}>
            <div className={styles.corner} role="columnheader">
              <span className={styles.hidden}>{rowHeader}</span>
            </div>
            {columns.map((column) => (
              <div key={column.id} className={styles.columnHeader} role="columnheader">
                {column.label}
              </div>
            ))}
          </div>
          {rows.map((row, r) => (
            <div key={row.id} className={styles.row} role="row" aria-rowindex={r + 2}>
              <div className={styles.rowHeader} role="rowheader" title={row.label}>
                {row.label}
              </div>
              {columns.map((column, c) => {
                const cell = loading ? MISSING : (row.cells[column.id] ?? MISSING);
                const isSelected = selectedAt?.r === r && selectedAt.c === c;
                const isActive = active.r === r && active.c === c;
                return (
                  <div
                    key={column.id}
                    ref={(node) => {
                      if (node) cellRefs.current.set(key(r, c), node);
                      else cellRefs.current.delete(key(r, c));
                    }}
                    className={`${styles.cell} ${toneStyles.tone}`}
                    role="gridcell"
                    data-tone={TONE[cell.status]}
                    data-loading={loading || undefined}
                    aria-selected={isSelected}
                    aria-label={`${row.label}, ${column.label}: ${words[cell.status]}${cell.text ? ` ${cell.text}` : ''}`}
                    tabIndex={isActive ? 0 : -1}
                    onClick={() => {
                      setFocus({ r, c });
                      choose(r, c);
                    }}
                    onKeyDown={(event) => {
                      onKeyDown(event, r, c);
                    }}
                    onFocus={() => {
                      if (!isActive) setFocus({ r, c });
                    }}
                  >
                    {loading ? null : cell.text}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
