/**
 * The feature table (GraphQL `FeatureTable`, ADR 0038) as the table widget reads it: one row
 * per instrument with its cells by catalogue name (a value, or the UNKNOWN code saying why
 * not), the columns' catalogue entries (their format comes from the server), and the query
 * that asks for a page of it (server-side filters, sort and paging).
 */
import type { PreviewRow } from '@/entities/screen';
import type { gqlTypes } from '@/shared/api';

/** The server-side filters (catalogue fields; text matches ignore case). */
export interface TableFilters {
  securityType?: string | undefined;
  sector?: string | undefined;
  liquidityClass?: string | undefined;
  leveraged?: boolean | undefined;
  optionable?: boolean | undefined;
  /** The symbol or name contains it. */
  q?: string | undefined;
}

export interface FeatureTableQuery {
  /** Catalogue names, in column order. */
  columns: readonly string[];
  /** The instruments to show (tickers or ids), in this order; absent: the universe. */
  keys?: readonly string[] | undefined;
  filters?: TableFilters | undefined;
  /** A column id (`symbol` or a catalogue name), `-` prefix descending; absent: the default. */
  sort?: string | undefined;
  /** Paging (1-based); absent: the first page of the API's default size. */
  page?: number | undefined;
  size?: number | undefined;
}

/** A cell: the value the server sent, or null with the code saying why. */
export interface TableCell {
  value: unknown;
  unknown: gqlTypes.UnknownCode | null;
  /** The public kind of the gap (ADR 0056): how the cell is drawn, never its code. */
  kind?: gqlTypes.UnavailableKind | null;
  /** That kind in the server's generic words. */
  kindText?: string | null;
  /** Why the null is the fact, when `unknown` is EXPLAINED (ADR 0046). */
  reason?: gqlTypes.NullReason | null;
}

type Served = NonNullable<gqlTypes.FeatureTableQuery['table']>;

/** The catalogue entry of a column, as the table reads it (its format from the server). */
export type ColumnInfo = Served['columns'][number];

/**
 * A table row: an instrument and its cells; a screener's result rows (a stored run, or the
 * Builder's preview) add their typed fields.
 */
export interface TableRow {
  /** The ticker: the row id (selection, the URL) and the key for detail reads. */
  symbol: string;
  instrumentId: string;
  name: string;
  /** Catalogue name -> cell. */
  cells: Readonly<Record<string, TableCell>>;
  rank?: number | undefined;
  decision?: string | undefined;
  score?: number | null | undefined;
  flags?: readonly string[] | undefined;
  /** Criterion id -> its value and outcome (PASS / NEAR / FAIL / MISSING). */
  criteria?: Readonly<Record<string, { value: unknown; outcome: string }>> | undefined;
  /** New or dropped since the previous run (decided by the server). */
  change?: string | null | undefined;
  /** The previous run's decision (null: not in it). */
  previousDecision?: string | null | undefined;
  /** The screen's display columns (`[columns]`): name -> the value the run stored. */
  columns?: Readonly<Record<string, unknown>> | undefined;
  /** Why the decision is not QUALIFIED. */
  reasons?: string | undefined;
  /** A preview row's criteria with their penalties: how its score was worked out. */
  scoring?: PreviewRow | undefined;
}

export interface FeatureTableData {
  session: string;
  /** What the nightly tables with no partition for the session leave out, and what the tables
   * the filters or the sort read have nothing for (no row passes a filter on them): by kind
   * (ADR 0056; `entities/availability` draws it). */
  unavailable: readonly Served['unavailable'][number][];
  /** The universe snapshot is from after the session (survivorship). */
  preSnapshot: boolean;
  columns: readonly ColumnInfo[];
  rows: TableRow[];
  /** Rows matching the filters (every page). */
  total: number;
  page: number;
  size: number;
}

/** The response's columnar table as rows. */
export function toTableData(table: Served): FeatureTableData {
  return {
    session: table.session.date,
    unavailable: [...table.session.unavailable, ...table.unavailable],
    preSnapshot: table.preSnapshot,
    columns: table.columns,
    rows: table.instruments.map((instrument, i) => {
      const values = table.rows[i] ?? [];
      const codes = table.unknown[i] ?? [];
      const reasons = table.reasons[i] ?? [];
      const kinds = table.kinds[i] ?? [];
      const texts = new Map(table.kindTexts.map((t) => [t.kind, t.text]));
      const cells: Record<string, TableCell> = {};
      table.columns.forEach((column, j) => {
        cells[column.name] = {
          value: values[j] ?? null,
          unknown: codes[j] ?? null,
          reason: reasons[j] ?? null,
          kind: kinds[j] ?? null,
          kindText: (kinds[j] && texts.get(kinds[j])) || null,
        };
      });
      return {
        symbol: instrument.symbol,
        instrumentId: instrument.instrumentId,
        name: instrument.name,
        cells,
      };
    }),
    total: table.total,
    page: table.page,
    size: table.size,
  };
}

/** The operation's variables for `query` (paging only when asked: the server's defaults). */
export function tableVariables(query: FeatureTableQuery): gqlTypes.FeatureTableQueryVariables {
  const f = query.filters ?? {};
  return {
    columns: [...query.columns],
    keys: query.keys ? [...query.keys] : null,
    securityType: f.securityType ?? null,
    sector: f.sector ?? null,
    liquidityClass: f.liquidityClass ?? null,
    leveraged: f.leveraged ?? null,
    optionable: f.optionable ?? null,
    q: f.q ?? null,
    sort: query.sort ?? null,
    // Absent, not null: the server's defaults apply (`page` and `size` are non-null there).
    ...(query.page !== undefined ? { page: query.page } : {}),
    ...(query.size !== undefined ? { size: query.size } : {}),
  };
}
