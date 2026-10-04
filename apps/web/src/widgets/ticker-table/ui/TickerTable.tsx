/**
 * The Explore ticker table: the whole universe for the latest session (about 11k rows,
 * virtualised) with the filter bar, columns chosen from the feature catalogue, sorting, and
 * row selection into the compare set. A row click focuses the ticker for the detail tabs. A
 * banner warns when the session is stale or some tables have no data for it.
 */
import { Banner, Box, DataTable, Panel, Stack, Text, type DataTableSort } from '@algotrade/ui';
import { useMemo } from 'react';

import { FeaturePicker } from '@/features/column-picker';
import { MAX_COMPARE, nextSelection } from '@/features/compare-set';
import {
  searchRows,
  TickerFilterBar,
  toTickerQuery,
  type TickerFilters,
} from '@/features/ticker-filter';
import { isStale, useTickerTable, useUniverseSize, type TickerRow } from '@/entities/explore';
import { byName, useFeatureCatalogue } from '@/entities/feature';

import { tickerColumns } from '../model/columns';

export interface TickerTableProps {
  filters: TickerFilters;
  onFiltersChange: (filters: TickerFilters) => void;
  /** Catalogue feature names shown as columns, in order. */
  columns: readonly string[];
  onColumnsChange: (columns: string[]) => void;
  sort: DataTableSort | null;
  onSortChange: (sort: DataTableSort | null) => void;
  /** The compare set (tickers), in pick order. */
  selected: readonly string[];
  onSelectedChange: (symbols: string[]) => void;
  onFocus: (symbol: string) => void;
}

const count = (n: number) => n.toLocaleString('en-US');

export function TickerTable({
  filters,
  onFiltersChange,
  columns,
  onColumnsChange,
  sort,
  onSortChange,
  selected,
  onSelectedChange,
  onFocus,
}: TickerTableProps) {
  const query = useMemo(() => toTickerQuery(filters, columns), [filters, columns]);
  const table = useTickerTable(query);
  const universe = useUniverseSize();
  const catalogue = useFeatureCatalogue();
  const known = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const tableColumns = useMemo(() => tickerColumns(columns, known), [columns, known]);
  const rows = useMemo(
    () => searchRows(table.data?.rows ?? [], filters.q),
    [table.data, filters.q],
  );

  const data = table.data;
  const summary = data
    ? `${count(rows.length)} of ${count(universe.data ?? data.total)} tickers · ${selected.length} selected`
    : 'Loading tickers…';
  return (
    <Panel
      title="Tickers"
      description={data ? `Session ${data.session}` : undefined}
      flush
      state={table.isError && !data ? 'error' : 'ready'}
      errorMessage="The ticker table failed to load."
      onRetry={() => void table.refetch()}
    >
      <Stack gap={0}>
        <Box padding={3}>
          <Stack gap={2}>
            {data && isStale(data.session) ? (
              <Banner asOf={data.session}>
                The latest stored session is old: a nightly run may have been missed.
              </Banner>
            ) : null}
            {data && (data.missing.length > 0 || data.preSnapshot) ? (
              <Banner tone="warning" title="Partial data">
                {data.preSnapshot ? 'The universe snapshot is from after this session. ' : ''}
                {data.missing.length > 0
                  ? `No data for this session in ${data.missing.join(', ')}: those columns are empty.`
                  : ''}
              </Banner>
            ) : null}
            <TickerFilterBar
              filters={filters}
              onChange={onFiltersChange}
              loading={table.isFetching}
            />
          </Stack>
        </Box>
        <DataTable<TickerRow>
          label="Tickers"
          columns={tableColumns}
          rows={rows}
          getRowId={(row) => row.symbol}
          getRowLabel={(row) => row.symbol}
          rowLines={2}
          visibleRows={16}
          sort={sort}
          onSortChange={onSortChange}
          selectable
          selectedIds={selected}
          onSelectionChange={(ids) => {
            onSelectedChange(nextSelection(selected, ids));
          }}
          onRowActivate={(row) => {
            onFocus(row.symbol);
          }}
          status={table.isPending ? 'loading' : 'ready'}
          emptyMessage={
            filters.q ? `No ticker matches “${filters.q}”` : 'No tickers match these filters'
          }
          toolbar={
            <Stack direction="row" gap={2} align="center" wrap>
              <Text size="sm" tone="muted">
                {summary}
                {selected.length >= MAX_COMPARE ? ` (compare holds ${MAX_COMPARE})` : ''}
              </Text>
              <FeaturePicker label="Columns" chosen={columns} onChange={onColumnsChange} />
            </Stack>
          }
        />
      </Stack>
    </Panel>
  );
}
