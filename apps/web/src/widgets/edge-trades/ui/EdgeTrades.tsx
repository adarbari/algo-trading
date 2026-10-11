/**
 * Section 5 of an edge's page, Trades: the picks of the verdict's basis (its screen and holding
 * period, never chosen here), one page at a time. The server sorts and pages them; the page only
 * says which (an In-sample / Out-of-sample / Live / All switch, a header click, Previous / Next)
 * and hands the same rows back as a CSV file. Live is off for an edge that records no paper
 * trades, with the live state's word and Guide term beside the switch (never "0 trades"). A per-name value the viewer may not read shows as
 * an unknown cell; a ledger that cannot be read (no run, pruned, never stored) says why in place
 * of the table. States: loading, error, unknown, ready.
 */
import {
  Button,
  DataTable,
  formatValue,
  ErrorState,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  type DataTableSort,
  type SegmentedOption,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { UnknownNote } from '@/entities/availability';
import {
  EDGE_UNKNOWN_WORDS,
  recordLabel,
  useEdgeLiveStates,
  useEdgeTrades,
  type EdgeTradeRow,
  type TradePeriod,
} from '@/entities/edge';
import { TradesCsvButton } from '@/features/edge-trades-csv';
import { termHelp } from '@/features/guide-help';

import { SORT_OF, tradeColumns } from '../model/columns';

const OPTIONS: SegmentedOption<TradePeriod>[] = [
  { value: 'ALL', label: 'All' },
  { value: 'IN_SAMPLE', label: 'In-sample' },
  { value: 'OUT_OF_SAMPLE', label: 'Out-of-sample' },
  { value: 'LIVE', label: 'Live' },
];

export interface EdgeTradesProps {
  edgeId: string;
}

export function EdgeTrades({ edgeId }: EdgeTradesProps) {
  const [period, setPeriod] = useState<TradePeriod>('ALL');
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<DataTableSort | null>({
    columnId: 'decision',
    direction: 'asc',
  });
  const columns = useMemo(() => tradeColumns(), []);
  const notRecording =
    useEdgeLiveStates().data?.find((s) => s.edgeId === edgeId)?.state === 'not_recording';
  const options = useMemo(
    () => OPTIONS.map((o) => (o.value === 'LIVE' && notRecording ? { ...o, disabled: true } : o)),
    [notRecording],
  );
  const query = useEdgeTrades({
    edgeId,
    period,
    page,
    sort: SORT_OF[sort?.columnId ?? 'decision'] ?? 'DECISION',
    descending: sort?.direction === 'desc',
  });
  const ledger = query.data;
  const choose = (next: TradePeriod) => {
    setPeriod(next);
    setPage(1);
  };
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
        <SegmentedControl
          aria-label="Filter trades"
          size="sm"
          options={options}
          value={period}
          onValueChange={choose}
        />
        {notRecording && (
          <>
            <Text
              tone="muted"
              size="sm"
            >{`Live: ${recordLabel('not_recording').toLowerCase()}`}</Text>
            {termHelp('live_state')}
          </>
        )}
        <Text tone="muted" size="sm">{`${String(ledger.total)} trades`}</Text>
        {ledger.symbolsSnapshot && (
          <Text tone="muted" size="sm">
            {`Tickers as of ${formatValue(ledger.symbolsSnapshot, { kind: 'date', style: 'short' }).text}`}
          </Text>
        )}
        <TradesCsvButton edgeId={edgeId} period={period} />
      </Stack>
      {ledger.unknown ? (
        <UnknownNote unknown={ledger.unknown} kindWords={EDGE_UNKNOWN_WORDS} />
      ) : ledger.oosHidden ? (
        <Stack direction="row" gap={1} align="center">
          <Text tone="secondary">Out-of-sample trades hidden</Text>
          {termHelp('show_out_of_sample')}
        </Stack>
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
            emptyMessage="No trades in this period"
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
