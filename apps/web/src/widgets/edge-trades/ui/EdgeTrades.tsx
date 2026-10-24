/**
 * Section 5 of an edge's page, Trades: the picks of the verdict's basis (its screen and holding
 * period, never chosen here), one page at a time. The server sorts and pages them; the page only
 * says which (the shared filter bar, ADR 0082: backtest or live, in sample, result, sector, return;
 * a header click, Previous / Next) and hands the period the filters stand for back as a CSV file.
 * The filters narrow the whole ledger before it is paged, and a change starts at page 1. An edge
 * that records no paper trades has the live state's word and Guide term beside the bar (never
 * "0 trades"). A per-name value the viewer may not read shows as
 * an unknown cell; a ledger that cannot be read (no run, pruned, never stored) says why in place
 * of the table. States: loading, error, unknown, ready.
 */
import {
  Button,
  DataTable,
  formatValue,
  ErrorState,
  Skeleton,
  Stack,
  Text,
  type DataTableSort,
} from '@algotrade/ui';
import { useCallback, useMemo, useState } from 'react';

import { UnknownNote } from '@/entities/availability';
import {
  EDGE_UNKNOWN_WORDS,
  recordLabel,
  useEdgeLiveStates,
  useEdgeTrades,
  type EdgeTradeRow,
} from '@/entities/edge';
import { TradesCsvButton } from '@/features/edge-trades-csv';
import { SurfaceFilterBar, SurfaceZeroResults, useFilterState } from '@/features/filter-bar';
import { termHelp } from '@/features/guide-help';

import { SORT_OF, tradeColumns } from '../model/columns';
import { periodOf } from '../model/period';

/** The surface of the filter bar: its definitions are `config/site/filters/edge_trades.toml`. */
const SURFACE = 'edge_trades';

export interface EdgeTradesProps {
  edgeId: string;
}

export function EdgeTrades({ edgeId }: EdgeTradesProps) {
  // The filters in force live in the widget (the edges route's `f` belongs to the list); the read
  // keeps the older default period `ALL`, which a `record` filter the viewer sets overrides.
  const [f, setF] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<DataTableSort | null>({
    columnId: 'decision',
    direction: 'asc',
  });
  const columns = useMemo(() => tradeColumns(), []);
  const notRecording =
    useEdgeLiveStates().data?.find((s) => s.edgeId === edgeId)?.state === 'not_recording';
  const filters = useFilterState(
    f,
    useCallback((next: string | undefined) => {
      setF(next);
      setPage(1); // a page of the old filters means nothing under the new ones
    }, []),
  );
  const period = periodOf(filters.filters);
  const query = useEdgeTrades({
    edgeId,
    period: 'ALL',
    filters: filters.filters,
    page,
    sort: SORT_OF[sort?.columnId ?? 'decision'] ?? 'DECISION',
    descending: sort?.direction === 'desc',
  });
  const ledger = query.data;
  const order = (next: DataTableSort | null) => {
    setSort(next);
    setPage(1);
  };
  if (query.isPending) return <Skeleton variant="rect" label="Loading the trades" />;
  if (query.isError || !ledger) {
    return (
      <ErrorState compact title="The trades failed to load." onRetry={() => void query.refetch()} />
    );
  }
  const last = page * ledger.pageSize >= ledger.total;
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={2} align="center" wrap>
        <Text weight="medium">Trades</Text>
        {termHelp('trade_ledger')}
        {notRecording && (
          <>
            <Text
              tone="muted"
              size="sm"
            >{`Live: ${recordLabel('not_recording').toLowerCase()}`}</Text>
            {termHelp('live_state')}
          </>
        )}
        {!query.isPlaceholderData && (
          <Text tone="muted" size="sm">{`${String(ledger.total)} trades`}</Text>
        )}
        {ledger.symbolsSnapshot && (
          <Text tone="muted" size="sm">
            {`Tickers as of ${formatValue(ledger.symbolsSnapshot, { kind: 'date', style: 'short' }).text}`}
          </Text>
        )}
        <TradesCsvButton edgeId={edgeId} period={period} />
      </Stack>
      <SurfaceFilterBar
        surface={SURFACE}
        views
        state={filters}
        facets={ledger.facets}
        help={(entry) => (entry.kind === 'term' ? termHelp(entry.id) : null)}
      />
      {ledger.unknown ? (
        <UnknownNote unknown={ledger.unknown} kindWords={EDGE_UNKNOWN_WORDS} />
      ) : ledger.oosHidden ? (
        <Stack direction="row" gap={1} align="center">
          <Text tone="secondary">Out-of-sample trades hidden</Text>
          {termHelp('show_out_of_sample')}
        </Stack>
      ) : query.isPlaceholderData ? (
        // The previous selection's rows are kept while the next load: never shown under the new one.
        <Skeleton variant="rect" label="Loading the trades" />
      ) : (
        <>
          <DataTable<EdgeTradeRow>
            label="Trade ledger"
            columns={columns}
            rows={ledger.rows}
            getRowId={(r) => `${r.decisionSession}:${r.instrumentId}:${r.variant}:${r.source}`}
            sortMode="server"
            sort={sort}
            onSortChange={order}
            emptyMessage={
              filters.filters.some((x) => x.active) ? (
                <SurfaceZeroResults surface={SURFACE} state={filters} facets={ledger.facets} />
              ) : (
                'No trades in this period'
              )
            }
            visibleRows={12}
          />
          <Stack direction="row" gap={2} align="center">
            <Button
              size="sm"
              variant="ghost"
              disabled={page <= 1}
              onClick={() => {
                setPage(page - 1);
              }}
            >
              Previous
            </Button>
            <Text tone="muted" size="sm">{`Page ${String(ledger.page)}`}</Text>
            <Button
              size="sm"
              variant="ghost"
              disabled={last}
              onClick={() => {
                setPage(page + 1);
              }}
            >
              Next
            </Button>
          </Stack>
        </>
      )}
    </Stack>
  );
}
