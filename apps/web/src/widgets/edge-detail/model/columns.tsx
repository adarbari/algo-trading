/**
 * The columns of an edge page's tables: the year-by-year rows of the verdict's basis, the tests
 * of the verdict (value, threshold, pass / fail / not measured) and the paper trades of a followed
 * edge. Rows are served records, not instruments; every figure and word is the server's.
 */
import { Mono, StatusBadge, type DataTableColumn, type StatusTone } from '@algotrade/ui';

import {
  tradeLabel,
  tradeTone,
  type PaperTrade,
  type VerdictCriterion,
  type VerdictYear,
} from '@/entities/edge';

export const yearColumns: DataTableColumn<VerdictYear>[] = [
  { id: 'year', header: 'Period', value: (y) => y.year, align: 'start', hideable: false },
  {
    id: 'win',
    header: 'Win rate',
    value: (y) => y.winRate,
    format: { kind: 'percent', digits: 0 },
    essential: true,
  },
  {
    id: 'base',
    header: 'Base rate',
    value: (y) => y.baseRate,
    format: { kind: 'percent', digits: 0 },
  },
  {
    id: 'lift',
    header: 'Lift',
    value: (y) => y.liftPts,
    format: { kind: 'delta', unit: 'points', digits: 0 },
    essential: true,
  },
  {
    id: 'spread',
    header: 'Top vs bottom decile',
    value: (y) => y.decileSpread,
    format: { kind: 'percent', digits: 1 },
  },
  { id: 'trades', header: 'Trades', value: (y) => y.trades, format: { kind: 'number' } },
];

const STATUS: Record<string, { label: string; tone: StatusTone }> = {
  pass: { label: 'Pass', tone: 'positive' },
  fail: { label: 'Fail', tone: 'negative' },
  not_measured: { label: 'Not measured yet', tone: 'neutral' },
};

export const criterionColumns: DataTableColumn<VerdictCriterion>[] = [
  { id: 'label', header: 'Test', value: (c) => c.label, grow: true, hideable: false },
  { id: 'value', header: 'Value', value: (c) => c.value, essential: true },
  { id: 'threshold', header: 'Needed', value: (c) => c.threshold },
  {
    id: 'status',
    header: 'Result',
    value: (c) => c.status,
    essential: true,
    cell: ({ row }) => {
      const s = STATUS[row.status] ?? { label: row.status, tone: 'neutral' as const };
      return <StatusBadge tone={s.tone}>{s.label}</StatusBadge>;
    },
  },
];

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
