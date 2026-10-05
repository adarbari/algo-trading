/**
 * The ticker table's filters, all applied by the server over the whole universe (the table is
 * paged there): security type, sector, liquidity class, leveraged, optionable and the search
 * text (the symbol or name contains it).
 */
import type { TableFilters } from '@/entities/feature';

export interface TickerFilters {
  /** The ticker or name contains it (case-insensitive). */
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

/** The feature table's server-side filters for these. */
export function toTableFilters(filters: TickerFilters): TableFilters {
  return {
    securityType: filters.type,
    sector: filters.sector,
    liquidityClass: filters.liquidity,
    leveraged: filters.leveraged,
    optionable: filters.optionable,
    q: filters.q?.trim() || undefined,
  };
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
