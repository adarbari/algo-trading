/**
 * The columns of the three signal tables: what to buy tonight, what to sell next session and the
 * followed edges with their record. Rows are served records; every figure and word is the
 * server's (the ticker is the instrument's symbol, else its id).
 */
import { Mono, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import { recordLabel, recordTone, type DeskTrade, type FollowedEdge } from '@/entities/edge';

const DATE = { kind: 'date', style: 'short' } as const;

const ticker: DataTableColumn<DeskTrade> = {
  id: 'ticker',
  header: 'Ticker',
  value: (t) => t.instrument?.symbol ?? t.instrumentId,
  cell: ({ row }) => <Mono weight="medium">{row.instrument?.symbol ?? row.instrumentId}</Mono>,
  align: 'start',
  hideable: false,
};

const edge: DataTableColumn<DeskTrade> = {
  id: 'edge',
  header: 'Edge',
  value: (t) => t.edgeName,
  grow: true,
  essential: true,
};

export const buyColumns: DataTableColumn<DeskTrade>[] = [
  ticker,
  edge,
  { id: 'rank', header: 'Rank', value: (t) => t.rank, format: { kind: 'number' } },
  { id: 'sell', header: 'Sell on', value: (t) => t.sellSession, format: DATE, essential: true },
];

export const sellColumns: DataTableColumn<DeskTrade>[] = [
  ticker,
  edge,
  { id: 'buy', header: 'Bought', value: (t) => t.buySession, format: DATE, essential: true },
];

export const followedColumns: DataTableColumn<FollowedEdge>[] = [
  { id: 'edge', header: 'Edge', value: (f) => f.name, grow: true, hideable: false },
  {
    id: 'record',
    header: 'Live record',
    value: (f) => f.record.state,
    essential: true,
    cell: ({ row }) => (
      <StatusBadge tone={recordTone(row.record.state)}>{recordLabel(row.record.state)}</StatusBadge>
    ),
  },
  {
    id: 'win',
    header: 'Win rate',
    value: (f) => f.record.winRate,
    format: { kind: 'percent', digits: 0 },
    essential: true,
  },
  { id: 'closed', header: 'Closed', value: (f) => f.record.closed, format: { kind: 'number' } },
  { id: 'open', header: 'Open', value: (f) => f.record.open, format: { kind: 'number' } },
];
