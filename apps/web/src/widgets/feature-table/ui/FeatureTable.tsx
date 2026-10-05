/**
 * The one table widget (ADR 0038): instruments x catalogue columns from the feature table,
 * built only from the column factories, with the column picker, sorting and paging.
 *
 * `sortMode="server"` (the universe): one page per request, filtered, sorted and paged by the
 * server, with the session notes (a stale session, nightly tables missing for it, a universe
 * snapshot from after it). `sortMode="client"` (a few instruments asked for by `keys`, e.g.
 * the compare set): every row in one request, sorted in the table. A row click focuses the
 * ticker; ticked rows are the caller's selection.
 */
import {
  Banner,
  Box,
  DataTable,
  IconButton,
  Panel,
  Stack,
  Text,
  type DataTableSort,
  type IconName,
} from '@algotrade/ui';
import { useMemo, useState, type ReactNode } from 'react';

import { FeaturePicker } from '@/features/column-picker';
import { isStale } from '@/entities/explore';
import { useFeatureTable, type TableFilters, type TableRow } from '@/entities/feature';

import { missingTables, pageCount, tablePlan } from '../model/plan';

export interface FeatureTableProps {
  /** The panel's title and the grid's name ("Tickers", "Side by side"). */
  label: string;
  /** Catalogue names shown as columns, in order (after the ticker). */
  columns: readonly string[];
  onColumnsChange: (columns: string[]) => void;
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
  const shape = JSON.stringify([columns, keys, filters, server ? sortParam(sort) : null]);
  // The page belongs to the query: any other query starts on its first page.
  const [paging, setPaging] = useState({ shape, page: 1 });
  const page = paging.shape === shape ? paging.page : 1;
  const table = useFeatureTable(
    server
      ? { columns, keys, filters, sort: sortParam(sort), page, size: pageSize }
      : { columns, keys, filters },
    !keys || keys.length > 0,
  );
  const data = table.data;
  const plan = useMemo(() => tablePlan(data?.columns ?? []), [data?.columns]);
  const rows: readonly TableRow[] = data?.rows ?? [];
  const pages = data ? pageCount(data.total, data.size) : 1;
  const missing = missingTables(data?.missing ?? []);
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
  const goTo = (next: number) => {
    setPaging({ shape, page: next });
  };
  const notes = server && data && (isStale(data.session) || missing.length > 0 || data.preSnapshot);
  return (
    <Panel
      title={label}
      description={data ? `Session ${data.session}` : undefined}
      flush
      state={table.isError && !data ? 'error' : 'ready'}
      errorMessage={`${label} failed to load.`}
      onRetry={() => void table.refetch()}
    >
      <Stack gap={0}>
        {header || notes ? (
          <Box padding={3}>
            <Stack gap={2}>
              {server && data && isStale(data.session) ? (
                <Banner asOf={data.session}>
                  The latest stored session is old: a nightly run may have been missed.
                </Banner>
              ) : null}
              {server && data && (missing.length > 0 || data.preSnapshot) ? (
                <Banner tone="warning" title="Partial data">
                  {data.preSnapshot ? 'The universe snapshot is from after this session. ' : ''}
                  {missing.length > 0
                    ? `Not stored for ${data.session}: ${missing.join(', ')}. Values from these tables read Unknown.`
                    : ''}
                </Banner>
              ) : null}
              {header}
            </Stack>
          </Box>
        ) : null}
        <DataTable<TableRow>
          label={label}
          columns={plan}
          rows={rows}
          getRowId={(row) => row.symbol}
          getRowLabel={(row) => row.symbol}
          rowLines={2}
          visibleRows={Math.min(visibleRows, Math.max(1, rows.length))}
          {...(sort !== undefined ? { sort } : {})}
          {...(onSortChange ? { onSortChange } : {})}
          sortMode={sortMode}
          selectable={selected !== undefined}
          selectedIds={selected ?? []}
          onSelectionChange={(ids) => {
            onSelectedChange?.(ids);
          }}
          onRowActivate={(row) => {
            onRowActivate?.(row.symbol);
          }}
          status={table.isPending && !data ? 'loading' : 'ready'}
          emptyMessage={table.data === null ? NOTHING_STORED : emptyMessage}
          toolbar={
            <Stack direction="row" gap={2} align="center" wrap>
              <Text size="sm" tone="muted">
                {summary}
              </Text>
              {server && data && pages > 1 ? (
                <Stack direction="row" gap={1} align="center">
                  <IconButton
                    icon="chevron-left"
                    label="Previous page"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => {
                      goTo(page - 1);
                    }}
                  />
                  <Text size="sm" tone="muted" numeric>
                    Page {count(page)} of {count(pages)}
                  </Text>
                  <IconButton
                    icon="chevron-right"
                    label="Next page"
                    size="sm"
                    disabled={page >= pages}
                    onClick={() => {
                      goTo(page + 1);
                    }}
                  />
                </Stack>
              ) : null}
              <FeaturePicker
                label={pickerLabel}
                icon={pickerIcon}
                chosen={columns}
                onChange={onColumnsChange}
              />
            </Stack>
          }
        />
      </Stack>
    </Panel>
  );
}
