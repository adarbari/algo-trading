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
  | { kind: 'cell'; figures: GridFigures; text: string; level: 1 | 2 | 3 }
  | { kind: 'unknown'; unknown: Pick<GridUnknown, 'kind' | 'guideTerm' | 'kindText'> };

export interface DisplayColumn {
  id: string;
  label: string;
  /** The days out (`7 days`). */
  sub: string | undefined;
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

/** The delta band label: `0.10` from a band of 0.10. */
export function bandLabel(band: number): string {
  return formatValue(band, { kind: 'number', digits: 2 }).text;
}

/** The column header: the expiry day (`Fri 30 Oct`), or the bucket's days when it has no expiry. */
export function columnLabel(column: GridExpiry): string {
  if (column.expiry === null) return `${column.bucket} days`;
  return formatValue(column.expiry, { kind: 'date', style: 'weekday' }).text;
}

/** The line under the header: the days out (`28 days`); empty without an expiry. */
export function columnSub(column: GridExpiry): string | undefined {
  return column.days === null ? undefined : `${column.days} days`;
}

/** The yield a year as the cell's text: `18.4%`. */
export function yieldText(yieldAnn: number): string {
  return formatValue(yieldAnn, { kind: 'percent', digits: 1 }).text;
}

/** One figure of the selected cell: the glossary term that names and explains it, and its text. */
export interface DetailFigure {
  term: string;
  value: string;
}

/** The figures of the selected cell, in the order the detail shows; each is named by its Guide term. */
export function detailFigures(figures: GridFigures): DetailFigure[] {
  const pct = (v: number, digits = 1) => formatValue(v, { kind: 'percent', digits }).text;
  const usd = (v: number) => formatValue(v, { kind: 'currency' }).text;
  return [
    { term: 'grid_strike', value: usd(figures.strike) },
    { term: 'grid_mid', value: usd(figures.mid) },
    { term: 'return_on_collateral', value: pct(figures.roc, 2) },
    { term: 'yield_a_year', value: pct(figures.yieldAnn) },
    { term: 'breakeven_price', value: usd(figures.breakeven) },
    { term: 'chance_below_strike', value: pct(figures.pBelow, 0) },
    { term: 'spread_of_mid', value: pct(figures.spreadPct) },
    { term: 'open_interest', value: formatValue(figures.openInterest, { kind: 'number' }).text },
  ];
}

/** The fill of a yield among the shown yields: 1 (faint), 2 or 3 (strong), by thirds of the range. */
export function heatLevel(yieldAnn: number, shown: readonly number[]): 1 | 2 | 3 {
  const low = Math.min(...shown);
  const high = Math.max(...shown);
  if (high <= low) return 2;
  const at = (yieldAnn - low) / (high - low);
  return at < 1 / 3 ? 1 : at < 2 / 3 ? 2 : 3;
}

/** The grid of one side as rows by delta band and columns by expiry bucket. */
export function gridView(grid: OptionGrid, side: GridSide): GridView {
  const columns: DisplayColumn[] = grid.columns.map((c) => ({
    id: String(c.bucket),
    label: columnLabel(c),
    sub: columnSub(c),
    days: c.days,
    reportInside: c.reportInside,
    gap: c.gap ?? null,
  }));
  // The server indexes a side as [column][band]: a row is one band across the columns.
  const shown = grid[side].flatMap((column) =>
    column.flatMap((cell) => (cell.__typename === 'GridCell' ? [cell.yieldAnn] : [])),
  );
  const rows = grid.bands.map((band, j): DisplayRow => {
    const cells: Record<string, DisplayCell> = {};
    columns.forEach((column, i) => {
      const cell = grid[side][i]?.[j];
      if (cell?.__typename === 'GridCell')
        cells[column.id] = {
          kind: 'cell',
          figures: cell,
          text: yieldText(cell.yieldAnn),
          level: heatLevel(cell.yieldAnn, shown),
        };
      else if (cell?.__typename === 'Unknown')
        cells[column.id] = { kind: 'unknown', unknown: cell };
      else if (column.gap) cells[column.id] = { kind: 'unknown', unknown: column.gap };
    });
    return { id: String(band), label: bandLabel(band), cells };
  });
  return { columns, rows };
}
