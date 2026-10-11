/**
 * The columns of the year-by-year table (the verdict's basis one calendar year or part year per
 * row) and of the deepest drawdowns (one episode per row). Rows are served records; every figure and label is the server's.
 */
import { Text, type DataTableColumn } from '@algotrade/ui';

import type { DrawdownEpisode, VerdictYear } from '@/entities/edge';

export const yearColumns: DataTableColumn<VerdictYear>[] = [
  { id: 'year', header: 'Period', value: (y) => y.label, align: 'start', hideable: false },
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

const PERCENT = { kind: 'percent', digits: 1 } as const;
const DATE = { kind: 'date', style: 'short' } as const;

export const episodeColumns: DataTableColumn<DrawdownEpisode>[] = [
  { id: 'peak', header: 'Peak', value: (e) => e.peak, format: DATE, hideable: false },
  { id: 'trough', header: 'Trough', value: (e) => e.trough, format: DATE },
  {
    id: 'recovered',
    header: 'Recovered',
    value: (e) => e.recovered,
    format: DATE,
    cell: ({ row, formatted }) => (
      <Text tone={row.recovered == null ? 'muted' : 'default'}>
        {row.recovered == null ? 'Not yet' : formatted.text}
      </Text>
    ),
  },
  { id: 'depth', header: 'Depth', value: (e) => e.depth, format: PERCENT, essential: true },
];
