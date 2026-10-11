/**
 * The columns of the trade ledger (one pick of the verdict's basis per row) and the server sort
 * each sortable column asks for. A per-name value the viewer may not read, or one not stored, is
 * an unknown cell with its word, never a number. Every figure, date and reason is the server's.
 */
import {
  Stack,
  StatusBadge,
  Text,
  type DataTableCellContext,
  type DataTableColumn,
} from '@algotrade/ui';

import { unknownWord } from '@/entities/availability';
import {
  excludedLabel,
  periodLabel,
  tradeStatusLabel,
  tradeStatusTone,
  type EdgeTradeRow,
  type TradeNumber,
  type TradeSort,
} from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

/** The server sort a column id asks for (a column not listed does not sort). */
export const SORT_OF: Record<string, TradeSort> = {
  decision: 'DECISION',
  exit: 'EXIT',
  instrument: 'SYMBOL',
  rank: 'RANK',
  status: 'STATUS',
  value: 'VALUE',
  score: 'SCORE',
  drawdown: 'DRAWDOWN',
  adv: 'ADV',
};

const DATE = { kind: 'date', style: 'short' } as const;

const WORDS: Record<string, string> = { LICENCE: 'Licensed', NOT_STORED: 'Not stored' };

/** A per-name number: its value formatted, or why it is not shown. */
const numberCell =
  (pick: (row: EdgeTradeRow) => TradeNumber) =>
  ({ row, formatted }: DataTableCellContext<EdgeTradeRow>) => {
    const cell = pick(row);
    if (cell.value == null) {
      const word = cell.unknown ? (WORDS[cell.unknown.kind] ?? unknownWord(cell.unknown)) : '—';
      return <Text tone="muted">{word}</Text>;
    }
    return <Text tone={formatted.tone}>{formatted.text}</Text>;
  };

const periodOf = (row: EdgeTradeRow): string =>
  row.source === 'live' ? 'live' : row.beforeSplit ? 'in_sample' : 'out_of_sample';

/** The ledger's columns (a function: the Guide buttons in two headers are built when the table is). */
export const tradeColumns = (): DataTableColumn<EdgeTradeRow>[] => [
  {
    id: 'decision',
    header: 'Decision',
    value: (r) => r.decisionSession,
    format: DATE,
    hideable: false,
    essential: true,
  },
  { id: 'entry', header: 'Entry', value: (r) => r.entrySession, format: DATE, sortable: false },
  { id: 'exit', header: 'Close', value: (r) => r.exitSession, format: DATE },
  {
    id: 'instrument',
    header: 'Ticker',
    value: (r) => r.symbol.value,
    mono: true,
    cell: ({ row, formatted }) =>
      row.symbol.value == null ? (
        <Text tone="muted">{row.symbol.unknown ? unknownWord(row.symbol.unknown) : '—'}</Text>
      ) : (
        <Text mono>{formatted.text}</Text>
      ),
    essential: true,
    hideable: false,
  },
  {
    id: 'company',
    header: 'Company',
    value: (r) => r.company.value,
    align: 'start',
    sortable: false,
    cell: ({ row }) =>
      row.company.value == null ? (
        <Text tone="muted">{row.company.unknown ? unknownWord(row.company.unknown) : '—'}</Text>
      ) : (
        <Text>{row.company.value}</Text>
      ),
  },
  { id: 'rank', header: 'Rank', value: (r) => r.rank, format: { kind: 'number' } },
  {
    id: 'score',
    header: 'Score at the decision',
    value: (r) => r.score.value,
    format: { kind: 'number', digits: 2 },
    cell: numberCell((r) => r.score),
  },
  {
    id: 'value',
    header: 'Result, net of cost',
    value: (r) => r.value.value,
    format: { kind: 'delta', unit: 'percent', digits: 1 },
    essential: true,
    cell: numberCell((r) => r.value),
  },
  {
    id: 'drawdown',
    header: 'Dip in the window',
    value: (r) => r.maxDrawdown,
    format: { kind: 'percent', digits: 1 },
  },
  {
    id: 'adv',
    header: '20-day dollar volume',
    value: (r) => r.advUsd.value,
    format: { kind: 'currency-compact' },
    cell: numberCell((r) => r.advUsd),
  },
  {
    id: 'status',
    header: 'Result',
    value: (r) => r.status,
    align: 'start',
    essential: true,
    cell: ({ row }) => (
      <Stack gap={0} align="start">
        <StatusBadge tone={tradeStatusTone(row.status)}>{tradeStatusLabel(row.status)}</StatusBadge>
        {row.excludedReason && (
          <Text tone="muted" size="sm">
            {excludedLabel(row.excludedReason)}
          </Text>
        )}
      </Stack>
    ),
    headerAction: termHelp('trade_status'),
  },
  {
    id: 'period',
    header: 'Period',
    value: (r) => periodLabel(periodOf(r)),
    sortable: false,
    headerAction: termHelp('trade_period'),
  },
];
