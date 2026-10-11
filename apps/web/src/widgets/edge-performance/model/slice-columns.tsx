/**
 * The columns of the two ways to cut the verdict basis besides the calendar: by market regime
 * (one row per regime, the figures of one period) and by holding period (one row per horizon, the
 * lift of each period). Every figure, state and date is the server's; a figure without a value
 * says its state in words, never a zero.
 */
import { Stack, StatusBadge, Text, type DataTableColumn } from '@algotrade/ui';

import {
  oosByLabel,
  regimeLabel,
  sliceStateLabel,
  type HorizonRow,
  type RegimeRow,
  type SliceFigure,
} from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

/** One regime with the figure of the period shown (none: the server sent no figure for it). */
export interface RegimeView {
  regime: string;
  figure: SliceFigure | undefined;
}

export const regimeViews = (rows: readonly RegimeRow[], period: string): RegimeView[] =>
  rows.map((row) => ({ regime: row.regime, figure: row.figures.find((f) => f.period === period) }));

const noValue = (figure: SliceFigure | undefined): string | null => {
  if (!figure) return 'Not stored';
  if (figure.state !== 'measured') return sliceStateLabel(figure.state);
  return figure.trades === 0 ? 'No trades' : null;
};

const PERCENT = { kind: 'percent', digits: 1 } as const;
const LIFT = { kind: 'delta', unit: 'points', digits: 1 } as const;

const figureColumn = (
  id: string,
  header: string,
  pick: (f: SliceFigure) => number | null,
  format: typeof PERCENT | typeof LIFT,
  essential = false,
): DataTableColumn<RegimeView> => ({
  id,
  header,
  value: (r) => (r.figure ? pick(r.figure) : null),
  format,
  essential,
  cell: ({ row, formatted }) => {
    const word = noValue(row.figure);
    return word ? (
      <Text tone="muted">{word}</Text>
    ) : (
      <Text tone={formatted.tone}>{formatted.text}</Text>
    );
  },
});

export const regimeColumns: DataTableColumn<RegimeView>[] = [
  {
    id: 'regime',
    header: 'Regime',
    value: (r) => regimeLabel(r.regime),
    align: 'start',
    hideable: false,
    cell: ({ row }) => (
      <Stack direction="row" gap={1} align="center">
        <Text>{regimeLabel(row.regime)}</Text>
        {row.regime === 'UNKNOWN' && termHelp('regime')}
      </Stack>
    ),
  },
  figureColumn('win', 'Win rate', (f) => f.winRate, PERCENT, true),
  figureColumn('base', 'Base rate', (f) => f.baseRate, PERCENT),
  figureColumn('lift', 'Lift', (f) => f.liftPts, LIFT, true),
  {
    id: 'trades',
    header: 'Trades',
    value: (r) => r.figure?.trades,
    format: { kind: 'number' },
    cell: ({ row, formatted }) => (
      <Stack direction="row" gap={1} align="center" justify="end">
        <Text>{formatted.text}</Text>
        {row.figure?.thin && (
          <>
            <Text tone="muted" size="sm">{`n=${String(row.figure.trades)}`}</Text>
            {termHelp('slice_state')}
          </>
        )}
      </Stack>
    ),
  },
];

const liftCell = (
  row: HorizonRow,
  period: string,
  formattedText: string,
  tone: 'default' | 'up' | 'down' | 'muted',
  notPreChosen: boolean,
) => {
  const figure = row.figures.find((f) => f.period === period);
  const word = noValue(figure);
  if (word) return <Text tone="muted">{word}</Text>;
  return (
    <Stack gap={0} align="end">
      <Stack direction="row" gap={1} align="center" justify="end">
        <Text tone={tone}>{formattedText}</Text>
        <Text tone="muted">{`(${String(figure?.trades ?? 0)})`}</Text>
      </Stack>
      {notPreChosen && (
        <Text tone="muted" size="sm">
          not the pre-chosen test
        </Text>
      )}
    </Stack>
  );
};

const periodColumn = (
  period: string,
  header: string,
  emphasis = false,
): DataTableColumn<HorizonRow> => ({
  id: period,
  header,
  value: (r) => r.figures.find((f) => f.period === period)?.liftPts,
  format: LIFT,
  emphasis,
  essential: emphasis,
  cell: ({ row, formatted }) =>
    liftCell(row, period, formatted.text, formatted.tone, emphasis && !row.basis),
});

/** The holding-period table; `needed` is the out-of-sample trade count the verdict asks for. */
export const horizonColumns = (needed: number): DataTableColumn<HorizonRow>[] => [
  {
    id: 'horizon',
    header: 'Holding period',
    value: (r) => r.horizon,
    align: 'start',
    hideable: false,
    cell: ({ row }) => (
      <Stack direction="row" gap={1} align="center" wrap>
        <Text>{`${String(row.horizon)} trading days`}</Text>
        {row.basis && (
          <>
            <StatusBadge tone="info">Verdict basis</StatusBadge>
            {termHelp('verdict_basis')}
          </>
        )}
      </Stack>
    ),
  },
  periodColumn('in_sample', 'In-sample'),
  periodColumn('out_of_sample', 'Out-of-sample', true),
  periodColumn('all', 'All'),
  {
    id: 'oos_by',
    header: `${String(needed)} OOS by`,
    value: (r) => r.oosBy.expectedBy,
    format: { kind: 'date', style: 'short' },
    cell: ({ row, formatted }) =>
      row.oosBy.state === 'projected' ? (
        <Text>{formatted.text}</Text>
      ) : (
        <Text tone="muted">{oosByLabel(row.oosBy.state)}</Text>
      ),
  },
];
