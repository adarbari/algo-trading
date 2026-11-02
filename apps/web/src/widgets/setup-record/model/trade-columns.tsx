/**
 * The columns of a followed setup's paper trades (the forward record). Rows are served records,
 * not instruments; every figure and word is the server's.
 */
import { Mono, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import { tradeLabel, tradeTone, type PaperTrade } from '@/entities/edge';

const DATE = { kind: 'date', style: 'short' } as const;

export const tradeColumns: DataTableColumn<PaperTrade>[] = [
  { id: 'signal', header: 'Signal', value: (t) => t.signalSession, format: DATE, hideable: false },
  {
    id: 'ticker',
    header: 'Ticker',
    value: (t) => t.instrument?.symbol ?? t.instrumentId,
    cell: ({ row }) => <Mono weight="medium">{row.instrument?.symbol ?? row.instrumentId}</Mono>,
    essential: true,
  },
  { id: 'rank', header: 'Rank', value: (t) => t.rank, format: { kind: 'number' } },
  { id: 'buy', header: 'Bought', value: (t) => t.buySession, format: DATE },
  { id: 'sell', header: 'Sell on', value: (t) => t.sellSession, format: DATE },
  {
    id: 'result',
    header: 'Result',
    value: (t) => t.status,
    essential: true,
    cell: ({ row }) => (
      <StatusBadge tone={tradeTone(row.status)}>{tradeLabel(row.status)}</StatusBadge>
    ),
  },
  {
    id: 'return',
    header: 'Return over the market',
    value: (t) => t.excessReturn,
    format: { kind: 'delta', unit: 'percent', digits: 1 },
    essential: true,
  },
  { id: 'reason', header: 'Why skipped', value: (t) => t.reason },
];
