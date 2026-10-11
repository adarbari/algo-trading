/**
 * The figures table of an edge's verdict: one row per figure, one column per side of the split
 * (in-sample, out-of-sample, all), the out-of-sample column marked and "n=" under a thin sample.
 * Every figure and every flag is the server's (`columns`); a figure it did not store reads as
 * missing, never zero.
 */
import { formatValue, Stack, Text, type DataTableColumn, type ValueFormat } from '@algotrade/ui';

import { periodLabel, type VerdictColumn } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

export interface FigureRow {
  id: string;
  label: string;
  /** The Guide term that explains the figure. */
  help: string;
  format: ValueFormat;
  value: (column: VerdictColumn) => number | null;
}

export const FIGURES: readonly FigureRow[] = [
  {
    id: 'win',
    label: 'Win rate',
    help: 'win_rate',
    format: { kind: 'percent', digits: 1 },
    value: (c) => c.winRate,
  },
  {
    id: 'base',
    label: 'Base rate',
    help: 'base_rate',
    format: { kind: 'percent', digits: 1 },
    value: (c) => c.baseRate,
  },
  {
    id: 'lift',
    label: 'Lift',
    help: 'lift',
    format: { kind: 'delta', unit: 'points', digits: 1 },
    value: (c) => c.liftPts,
  },
  {
    id: 'trades',
    label: 'Trades',
    help: 'trades',
    format: { kind: 'number' },
    value: (c) => c.trades,
  },
  {
    id: 'spread',
    label: 'Top vs bottom decile',
    help: 'top_vs_bottom_decile',
    format: { kind: 'delta', unit: 'percent', digits: 2 },
    value: (c) => c.decileSpread,
  },
  {
    id: 'decile-t',
    label: 'Decile t',
    help: 'top_vs_bottom_decile',
    format: { kind: 'number', digits: 2 },
    value: (c) => c.decileT,
  },
  {
    id: 'sharpe',
    label: 'Sharpe',
    help: 'sharpe_ratio',
    format: { kind: 'number', digits: 2 },
    value: (c) => c.sharpe,
  },
  {
    id: 'dsr',
    label: 'Deflated Sharpe',
    help: 'deflated_sharpe',
    format: { kind: 'number', digits: 2 },
    value: (c) => c.deflatedSharpe,
  },
  {
    id: 'pbo',
    label: 'Chance of overfitting',
    help: 'overfitting_probability',
    format: { kind: 'number', digits: 2 },
    value: (c) => c.pbo,
  },
];

/** The rows only an expires-out-of-the-money outcome has; shown when any side stored one. */
export const RATE_FIGURES: readonly FigureRow[] = [
  {
    id: 'reference',
    label: 'Risk-neutral rate',
    help: 'reference_rate',
    format: { kind: 'percent', digits: 1 },
    value: (c) => c.referenceRate,
  },
  {
    id: 'touch',
    label: 'Touch rate',
    help: 'touch_rate',
    format: { kind: 'percent', digits: 1 },
    value: (c) => c.touchRate,
  },
];

/** The figure rows of a verdict's columns: the common ones, then the rates when stored. */
export function figureRows(columns: readonly VerdictColumn[]): readonly FigureRow[] {
  const stored = RATE_FIGURES.filter((row) => columns.some((c) => row.value(c) != null));
  return stored.length === 0 ? FIGURES : [...FIGURES, ...stored];
}

const OUT = 'out_of_sample';

/** The column of one side of the split; its header says "n=" when the sample is thin. */
function sideColumn(side: VerdictColumn): DataTableColumn<FigureRow> {
  return {
    id: side.period,
    header:
      side.thin && side.trades != null
        ? `${periodLabel(side.period)} · n=${String(side.trades)}`
        : periodLabel(side.period),
    value: (row) => row.value(side),
    emphasis: side.period === OUT,
    sortable: false,
    essential: side.period !== 'all',
    cell: ({ row }) => {
      const shown = formatValue(row.value(side), row.format);
      return <Text tone={shown.tone}>{shown.text}</Text>;
    },
  };
}

export function figureColumns(columns: readonly VerdictColumn[]): DataTableColumn<FigureRow>[] {
  return [
    {
      id: 'figure',
      header: 'Figure',
      value: (row) => row.label,
      sortable: false,
      hideable: false,
      grow: true,
      cell: ({ row }) => (
        <Stack direction="row" gap={1} align="center">
          <Text size="sm">{row.label}</Text>
          {termHelp(row.help)}
        </Stack>
      ),
    },
    ...columns.map(sideColumn),
  ];
}
