/**
 * ExpandableTable: a table whose rows open their detail in place (a screener's criteria, today's
 * run and hits). Columns line up under a header row; each row's first cell holds the toggle (a
 * button with `aria-expanded`, its stretched hit area covers the whole row) and the other cells
 * are plain. In a narrow container (phone) only the columns marked `narrow` stay and the header
 * follows. Controlled by the caller, so a list keeps one row open at a time; the detail is
 * rendered only while open, so it can load lazily. With `rowToggle={false}` the rows carry no
 * toggle: a control inside a cell (a link, an `ExpandLink`) opens the row's detail, the other
 * cells keep their own links and buttons, and a narrow container shows each row as a card of
 * stacked cells under no header. A row with `onActivate` also opens its page when clicked outside
 * its own controls (the pointer shows it). For a flat list of rows use ExpandableRow;
 * for sortable, virtualised data DataTable.
 */
import { useId, type CSSProperties, type ReactNode } from 'react';

import { Icon } from '../Icon';
import styles from './ExpandableTable.module.css';

export interface ExpandableTableColumn {
  id: string;
  /** The column header. */
  label: ReactNode;
  /** `end` right-aligns a number column (default `start`). */
  align?: 'start' | 'end';
  /** Share of the row's width (default 1; the first column usually takes 2). */
  grow?: number;
  /** Kept on a phone; the other columns drop out of a narrow container. */
  narrow?: boolean;
}

export interface ExpandableTableRow {
  id: string;
  /** The cells by column id. The first column's cell names the toggle: keep it phrasing content. */
  cells: Readonly<Record<string, ReactNode>>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Shown in place under the row while open. */
  detail: ReactNode;
  /**
   * Choosing the row (a click on a part of it that is not itself a link, button or field) goes to
   * the row's page. The keyboard way in stays a control inside a cell, so the row adds no tab stop.
   */
  onActivate?: () => void;
}

export interface ExpandableTableProps {
  columns: readonly ExpandableTableColumn[];
  rows: readonly ExpandableTableRow[];
  /** Accessible name of the table. */
  label: string;
  /** `false`: no row toggle, cells hold their own controls and a phone shows cards (default `true`). */
  rowToggle?: boolean;
}

/** What inside a row handles its own click. */
const INTERACTIVE = 'a, button, input, select, textarea, label, [role="button"], [role="link"]';

const track = (column: ExpandableTableColumn) => `minmax(0, ${String(column.grow ?? 1)}fr)`;

function TableRow({
  row,
  columns,
  rowToggle,
}: {
  row: ExpandableTableRow;
  columns: readonly ExpandableTableColumn[];
  rowToggle: boolean;
}) {
  const id = useId();
  return (
    <>
      {/* A pointer shortcut: the keyboard way in is the control inside a cell (a link to the page). */}
      {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/interactive-supports-focus */}
      <div
        role="row"
        className={styles.row}
        data-open={row.open || undefined}
        data-activatable={row.onActivate ? true : undefined}
        onClick={
          row.onActivate
            ? (event) => {
                if (!(event.target as Element).closest(INTERACTIVE)) row.onActivate?.();
              }
            : undefined
        }
      >
        {columns.map((column, index) => (
          <div
            key={column.id}
            role="cell"
            className={styles.cell}
            data-align={column.align}
            data-wide={column.narrow ? undefined : true}
          >
            {rowToggle && index === 0 ? (
              <button
                type="button"
                className={styles.toggle}
                aria-expanded={row.open}
                aria-controls={row.open ? `${id}-detail` : undefined}
                onClick={() => {
                  row.onOpenChange(!row.open);
                }}
              >
                <Icon name="chevron-right" size="sm" tone="muted" />
                {row.cells[column.id]}
              </button>
            ) : (
              row.cells[column.id]
            )}
          </div>
        ))}
      </div>
      {row.open && (
        <div role="row" id={`${id}-detail`} className={styles.detail}>
          <div role="cell">{row.detail}</div>
        </div>
      )}
    </>
  );
}

export function ExpandableTable({ columns, rows, label, rowToggle = true }: ExpandableTableProps) {
  const wide = columns.map(track).join(' ');
  const narrow = columns
    .filter((c) => c.narrow)
    .map(track)
    .join(' ');
  return (
    <div
      role="table"
      aria-label={label}
      className={styles.root}
      data-cards={rowToggle ? undefined : true}
      style={{ '--et-wide': wide, '--et-narrow': narrow } as CSSProperties}
    >
      <div role="row" className={`${styles.row} ${styles.head}`}>
        {columns.map((column) => (
          <div
            key={column.id}
            role="columnheader"
            className={styles.cell}
            data-align={column.align}
            data-wide={column.narrow ? undefined : true}
          >
            {column.label}
          </div>
        ))}
      </div>
      {rows.map((row) => (
        <TableRow key={row.id} row={row} columns={columns} rowToggle={rowToggle} />
      ))}
    </div>
  );
}
