/**
 * The columns of an edge page's two tables: the year-by-year rows of the verdict's basis and the
 * tests of the verdict (value, threshold, pass / fail / not measured). Rows are served records,
 * not instruments; every figure and word is the server's.
 */
import { StatusBadge, type DataTableColumn, type StatusTone } from '@algotrade/ui';

import type { VerdictCriterion, VerdictYear } from '@/entities/edge';

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
