/**
 * The ticker table's filters: server-side ones (security type, sector, liquidity class,
 * leveraged, optionable: they change which rows the API returns) and the search text, matched
 * locally over the loaded rows so typing never waits for the network.
 */
import type { TickerQuery, TickerRow } from '@/entities/explore';

export interface TickerFilters {
  /** Ticker, name or any text column contains (case-insensitive). */
  q?: string | undefined;
  /** Security type (`COMMON_STOCK`, `ETF`, `ADR`, ...). */
  type?: string | undefined;
  sector?: string | undefined;
  /** Liquidity class (`HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`). */
  liquidity?: string | undefined;
  leveraged?: boolean | undefined;
  optionable?: boolean | undefined;
}

/** The security types offered as chips (the rest through "+ Filter"). */
export const TYPE_CHIPS: readonly { value: string; label: string }[] = [
  { value: 'COMMON_STOCK', label: 'Stock' },
  { value: 'ETF', label: 'ETF' },
  { value: 'ADR', label: 'ADR' },
];

/** The API query for these filters and catalogue columns (the search text stays local). */
export function toTickerQuery(filters: TickerFilters, columns: readonly string[]): TickerQuery {
  return {
    securityType: filters.type,
    sector: filters.sector,
    liquidityClass: filters.liquidity,
    leveraged: filters.leveraged,
    optionable: filters.optionable,
    columns,
  };
}

/** Does the row match the search text (ticker, name, or a text value such as the sector)? */
export function matchesSearch(row: TickerRow, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (row.symbol.toLowerCase().includes(q) || row.name.toLowerCase().includes(q)) return true;
  return Object.values(row.values).some(
    (v) => typeof v === 'string' && v.toLowerCase().includes(q),
  );
}

/** Rows matching the search, in their order; exact ticker matches first. */
export function searchRows(
  rows: readonly TickerRow[],
  query: string | undefined,
): readonly TickerRow[] {
  const q = (query ?? '').trim();
  if (!q) return rows;
  const exact = q.toUpperCase();
  const found = rows.filter((row) => matchesSearch(row, q));
  const first = found.filter((r) => r.symbol === exact);
  return first.length > 0 ? [...first, ...found.filter((r) => r.symbol !== exact)] : found;
}

/** The type in words: `COMMON_STOCK` -> `Common stock`. */
export function typeLabel(type: string): string {
  const chip = TYPE_CHIPS.find((t) => t.value === type);
  if (chip) return chip.label;
  const words = type.replace(/_/g, ' ').toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** `HIGH` -> `High`. */
export function liquidityLabel(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}
