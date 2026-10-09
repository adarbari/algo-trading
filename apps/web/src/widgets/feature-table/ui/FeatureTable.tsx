/**
 * The universe's (or the instruments asked for) instruments x catalogue columns, from the
 * feature table (GraphQL `Query.table`), with the column picker, sorting and paging.
 *
 * `sortMode="server"` (the universe): one page per request, filtered, sorted and paged by the
 * server, with the table's notes (nightly tables missing for it, a universe
 * snapshot from after it). `sortMode="client"` (a few instruments asked for by `keys`, e.g.
 * the compare set): every row in one request, sorted in the table. A row click focuses the
 * ticker; ticked rows are the caller's selection.
 */
import type { DataTableSort, IconName } from '@algotrade/ui';
import { useMemo, type ReactNode } from 'react';

import { FeaturePicker } from '@/features/column-picker';
import {
  useFeatureTable,
  withCompanions,
  type TableFilters,
  type TableRow,
} from '@/entities/feature';

import { usePageOf } from '../model/paging';
import { pageCount, tablePlan } from '../model/plan';

import { TableFrame } from './TableFrame';

export interface FeatureTableProps {
  /** The panel's title and the grid's name ("Tickers", "Side by side"). */
  label: string;
  /** Catalogue names shown as columns, in order (after the ticker). */
  columns: readonly string[];
  onColumnsChange: (columns: string[]) => void;
  /** The columns added back on a narrow table (the page keeps them in its URL); absent: the table keeps them. */
  narrowColumns?: readonly string[];
  onNarrowColumnsChange?: (columns: string[]) => void;
  /** The column picker's trigger ("Columns", "Dimension") and icon. */
  pickerLabel?: string;
  pickerIcon?: IconName;
  /** The instruments to show (tickers), in this order; absent: the universe. */
  keys?: readonly string[];
  filters?: TableFilters;
  /** `server`: the server sorts and pages (the universe); `client`: the table sorts the rows. */
  sortMode: 'server' | 'client';
  /** Controlled sort (server mode: sent to the server); absent: the table keeps its own. */
  sort?: DataTableSort | null;
  onSortChange?: (sort: DataTableSort | null) => void;
  /** Rows per page (server mode). */
  pageSize?: number;
  /** Above the table: filters. */
  header?: ReactNode;
  /** Ticked rows (tickers); absent: no checkboxes. */
  selected?: readonly string[];
  onSelectedChange?: (symbols: string[]) => void;
  /** The most rows the selection holds (said in the summary when reached). */
  maxSelected?: number;
  onRowActivate?: (symbol: string) => void;
  emptyMessage: ReactNode;
  visibleRows?: number;
}

const DEFAULT_PAGE_SIZE = 100;
/** The server answered with no table: nothing is stored yet to resolve a session from. */
const NOTHING_STORED = 'Nothing stored yet: tickers appear after the first nightly run.';
const count = (n: number) => n.toLocaleString('en-US');
const sortParam = (sort: DataTableSort | null | undefined) =>
  sort ? `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}` : undefined;

export function FeatureTable({
  label,
  columns,
  onColumnsChange,
  narrowColumns,
  onNarrowColumnsChange,
  pickerLabel = 'Columns',
  pickerIcon = 'columns',
  keys,
  filters,
  sortMode,
  sort,
  onSortChange,
  pageSize = DEFAULT_PAGE_SIZE,
  header,
  selected,
  onSelectedChange,
  maxSelected,
  onRowActivate,
  emptyMessage,
  visibleRows = 16,
}: FeatureTableProps) {
  const server = sortMode === 'server';
  const [page, setPage] = usePageOf(
    JSON.stringify([columns, keys, filters, server ? sortParam(sort) : null]),
  );
  const asked = useMemo(() => withCompanions(columns), [columns]);
  const table = useFeatureTable(
    server
      ? { columns: asked, keys, filters, sort: sortParam(sort), page, size: pageSize }
      : { columns: asked, keys, filters },
    !keys || keys.length > 0,
  );
  const data = table.data;
  const plan = useMemo(() => tablePlan(data?.columns ?? [], columns), [data?.columns, columns]);
  const rows: readonly TableRow[] = data?.rows ?? [];
  const full = maxSelected !== undefined && (selected?.length ?? 0) >= maxSelected;
  const summary = data
    ? [
        `${count(data.total)} ${data.total === 1 ? 'ticker' : 'tickers'}`,
        ...(selected
          ? [`${selected.length} selected${full ? ` (at most ${maxSelected})` : ''}`]
          : []),
      ].join(' · ')
    : table.isPending
      ? 'Loading tickers…'
      : NOTHING_STORED;
  return (
    <TableFrame
      panel={{
        title: label,
        description: data ? `Session ${data.session}` : undefined,
        state: table.isError && !data ? 'error' : 'ready',
        errorMessage: `${label} failed to load.`,
        onRetry: () => void table.refetch(),
      }}
      notes={server ? data : null}
      header={header}
      summary={summary}
      pager={
        server && data ? { page, pages: pageCount(data.total, data.size), onPage: setPage } : null
      }
      controls={
        <FeaturePicker
          label={pickerLabel}
          icon={pickerIcon}
          chosen={columns}
          onChange={onColumnsChange}
        />
      }
      grid={{
        label,
        columns: plan,
        rows,
        visibleRows: Math.min(visibleRows, Math.max(1, rows.length)),
        ...(sort !== undefined ? { sort } : {}),
        ...(onSortChange ? { onSortChange } : {}),
        sortMode,
        ...(narrowColumns !== undefined ? { narrowColumns } : {}),
        ...(onNarrowColumnsChange ? { onNarrowColumnsChange } : {}),
        selectable: selected !== undefined,
        selectedIds: selected ?? [],
        onSelectionChange: (ids) => {
          onSelectedChange?.(ids);
        },
        onRowActivate: (row) => {
          onRowActivate?.(row.symbol);
        },
        status: table.isPending && !data ? 'loading' : 'ready',
        emptyMessage: table.data === null ? NOTHING_STORED : emptyMessage,
      }}
    />
  );
}
