/**
 * An option grid shaped for display: rows by delta band, columns by expiry bucket, one side
 * (puts or calls) at a time. A cell is its figures formatted with the design system's
 * formatter, or the public kind of why there is none (never blank, never zero). Open interest
 * the server did not know stays unknown. Nothing is derived here: every figure is the server's.
 */
import { formatValue } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

type GridInstrument = NonNullable<gqlTypes.OptionGridQuery['instrument']>;
type GridResult = GridInstrument['optionGrid'];
export type OptionGrid = Extract<GridResult, { __typename: 'OptionGrid' }>;
export type GridUnknown = Extract<GridResult, { __typename: 'Unknown' }>;
export type GridExpiry = OptionGrid['columns'][number];
export type GridSide = 'puts' | 'calls';

/** A cell with its figures as the server sent them (a fraction is a fraction). */
export interface GridFigures {
  strike: number;
  delta: number;
  iv: number;
  mid: number;
  roc: number;
  yieldAnn: number;
  breakeven: number;
  pBelow: number;
  spreadPct: number;
  openInterest: number | null;
}

export type DisplayCell =
  | { kind: 'cell'; figures: GridFigures; text: string }
  | { kind: 'unknown'; unknown: Pick<GridUnknown, 'kind' | 'guideTerm' | 'kindText'> };

export interface DisplayColumn {
  id: string;
  label: string;
  /** The expiry's days from the session (null: the bucket has no expiry). */
  days: number | null;
  /** True a report falls inside; null when unknown or the bucket has no expiry. */
  reportInside: boolean | null;
  gap: Pick<GridUnknown, 'kind' | 'guideTerm' | 'kindText'> | null;
}

export interface DisplayRow {
  id: string;
  label: string;
  cells: Readonly<Record<string, DisplayCell>>;
}

export interface GridView {
  columns: DisplayColumn[];
  rows: DisplayRow[];
}

/** The grid itself, or null when the server answered with why there is none. */
export function gridOf(instrument: GridInstrument | null | undefined): OptionGrid | null {
  const grid = instrument?.optionGrid;
  return grid?.__typename === 'OptionGrid' ? grid : null;
}

/** Why there is no grid (null: there is one, or nothing is read yet). */
export function gridUnknown(instrument: GridInstrument | null | undefined): GridUnknown | null {
  const grid = instrument?.optionGrid;
  return grid?.__typename === 'Unknown' ? grid : null;
}

/** The delta band label: `10Δ` from a band of 0.10. */
export function bandLabel(band: number): string {
  return `${Math.round(band * 100)}Δ`;
}

/** The column label: the expiry day and its days out (`20 Nov · 19d`), or the bucket's days. */
export function columnLabel(column: GridExpiry): string {
  if (column.expiry === null || column.days === null) return `Bucket ${column.bucket}`;
  const day = formatValue(column.expiry, { kind: 'date', style: 'day' }).text;
  return `${day} · ${column.days}d`;
}

/** The yield a year as the cell's text: `18.4%`. */
export function yieldText(yieldAnn: number): string {
  return formatValue(yieldAnn, { kind: 'percent', digits: 1 }).text;
}

/** The figures of the selected cell as `[label, text]` pairs, in the order the detail shows. */
export function detailLines(figures: GridFigures): [string, string][] {
  const pct = (v: number, digits = 1) => formatValue(v, { kind: 'percent', digits }).text;
  return [
    ['Strike', formatValue(figures.strike, { kind: 'currency' }).text],
    ['Our mid', formatValue(figures.mid, { kind: 'currency' }).text],
    ['Return on collateral', pct(figures.roc, 2)],
    ['Yield a year', pct(figures.yieldAnn)],
    ['Breakeven', formatValue(figures.breakeven, { kind: 'currency' }).text],
    ['Chance below strike', pct(figures.pBelow, 0)],
    ['Spread (of mid)', pct(figures.spreadPct)],
    ['Open interest', formatValue(figures.openInterest, { kind: 'number' }).text],
  ];
}

/** The grid of one side as rows by delta band and columns by expiry bucket. */
export function gridView(grid: OptionGrid, side: GridSide): GridView {
  const columns: DisplayColumn[] = grid.columns.map((c) => ({
    id: String(c.bucket),
    label: columnLabel(c),
    days: c.days,
    reportInside: c.reportInside,
    gap: c.gap ?? null,
  }));
  // The server indexes a side as [column][band]: a row is one band across the columns.
  const rows = grid.bands.map((band, j): DisplayRow => {
    const cells: Record<string, DisplayCell> = {};
    columns.forEach((column, i) => {
      const cell = grid[side][i]?.[j];
      if (cell?.__typename === 'GridCell')
        cells[column.id] = { kind: 'cell', figures: cell, text: yieldText(cell.yieldAnn) };
      else if (cell?.__typename === 'Unknown')
        cells[column.id] = { kind: 'unknown', unknown: cell };
      else if (column.gap) cells[column.id] = { kind: 'unknown', unknown: column.gap };
    });
    return { id: String(band), label: bandLabel(band), cells };
  });
  return { columns, rows };
}
