/**
 * The Explore ticker table: the universe for a session as rows of tickers x requested
 * catalogue columns, and the query that asks for it (server-side filters + columns).
 */
import type { components } from '@/shared/api';

/** Server-side filters and the catalogue columns to fetch. */
export interface TickerQuery {
  securityType?: string | undefined;
  sector?: string | undefined;
  liquidityClass?: string | undefined;
  leveraged?: boolean | undefined;
  optionable?: boolean | undefined;
  columns: readonly string[];
}

export interface TickerRow {
  /** The ticker: the row id, the URL's selection key and the API key for detail reads. */
  symbol: string;
  instrumentId: string;
  name: string;
  securityType: string;
  /** Feature name -> value (null: unknown for this instrument). */
  values: Readonly<Record<string, unknown>>;
}

export interface TickerTableData {
  rows: TickerRow[];
  /** Rows matching the filters (every page fetched). */
  total: number;
  session: string;
  snapshotDate: string;
  preSnapshot: boolean;
  /** Tables with no partition for the session (their columns are null). */
  missing: string[];
  columns: string[];
}

type TickerPage = components['schemas']['TickerTable'];

/** The API's query parameters for one page. */
export function tickerParams(query: TickerQuery, page: number, size: number) {
  return {
    page,
    size,
    columns: query.columns.length > 0 ? query.columns.join(',') : null,
    security_type: query.securityType ?? null,
    sector: query.sector ?? null,
    liquidity_class: query.liquidityClass ?? null,
    leveraged: query.leveraged ?? null,
    optionable: query.optionable ?? null,
  };
}

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

export function toTickerRow(item: Readonly<Record<string, unknown>>): TickerRow {
  const { instrument_id: id, symbol, company_name: name, security_type: type, ...values } = item;
  return {
    symbol: text(symbol),
    instrumentId: text(id),
    name: text(name),
    securityType: text(type),
    values,
  };
}

/** Joins the pages of one query (page 1 first) into the table. */
export function joinPages(pages: readonly TickerPage[]): TickerTableData {
  const [first] = pages;
  if (!first) throw new Error('joinPages: no pages');
  return {
    rows: pages.flatMap((p) => p.page.items.map(toTickerRow)),
    total: first.page.total,
    session: first.session,
    snapshotDate: first.snapshot_date,
    preSnapshot: first.pre_snapshot,
    missing: first.missing,
    columns: first.columns,
  };
}
