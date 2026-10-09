/**
 * The columns of an edge page's tables: the year-by-year rows of the verdict's basis, the
 * tests of the verdict (value, threshold, pass / fail / not measured) and a copy's comparison. Rows are served records,
 * not instruments; every figure and word is the server's.
 */
import { Stack, StatusBadge, Text, type DataTableColumn, type StatusTone } from '@algotrade/ui';

import type { CompareRow, VerdictCriterion, VerdictYear } from '@/entities/edge';

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

/** The comparison of a copy with the edge it extends and the baselines: in-sample, then
 * out-of-sample (left out while the server withholds it until the user shows it). */
export function compareColumns(withOos: boolean): DataTableColumn<CompareRow>[] {
  const inSample: DataTableColumn<CompareRow>[] = [
    {
      id: 'label',
      header: 'Version',
      value: (r) => r.label,
      grow: true,
      hideable: false,
      cell: ({ row }) => (
        <Stack gap={0}>
          <Text size="sm" weight="medium">
            {row.label}
          </Text>
          <Text size="xs" tone="muted">
            {row.basis}
          </Text>
        </Stack>
      ),
    },
    {
      id: 'is_win',
      header: 'In-sample win rate',
      value: (r) => r.inSample?.winRate ?? null,
      format: { kind: 'percent', digits: 0 },
      essential: true,
    },
    {
      id: 'is_lift',
      header: 'In-sample lift',
      value: (r) => r.inSample?.liftPts ?? null,
      format: { kind: 'delta', unit: 'points', digits: 0 },
    },
    {
      id: 'is_trades',
      header: 'In-sample trades',
      value: (r) => r.inSample?.trades ?? null,
      format: { kind: 'number' },
    },
  ];
  if (!withOos) return inSample;
  return [
    ...inSample,
    {
      id: 'oos_win',
      header: 'Out-of-sample win rate',
      value: (r) => r.outOfSample?.winRate ?? null,
      format: { kind: 'percent', digits: 0 },
      essential: true,
    },
    {
      id: 'oos_lift',
      header: 'Out-of-sample lift',
      value: (r) => r.outOfSample?.liftPts ?? null,
      format: { kind: 'delta', unit: 'points', digits: 0 },
    },
    {
      id: 'oos_trades',
      header: 'Out-of-sample trades',
      value: (r) => r.outOfSample?.trades ?? null,
      format: { kind: 'number' },
    },
  ];
}
