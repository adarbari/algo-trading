/**
 * The top-ideas table's columns: rank, ticker, the screeners that picked it (by name; each
 * opens that screener's results), the best decision, score, the served facts for the session
 * (next earnings, else when the last one was; days to the nearest expiry, flagged when the
 * server says earnings come first; IV30), the screeners' stored display values (HV30, IV / HV
 * and the best put) and the watch-outs. A fact or display-value column appears only when some
 * idea has a value for it.
 */
import {
  Button,
  Mono,
  Stack,
  StatusBadge,
  Text,
  type DataTableColumn,
  type ValueFormat,
} from '@algotrade/ui';

import { valueFormat } from '@/entities/feature';
import { earningsBeforeExpiry, factOf, IDEA_FACTS, type Idea } from '@/entities/idea';
import { DecisionBadge } from '@/entities/screen';

import { dteReason, earningsCell, expiryDte, iv30, nextEarnings } from './facts';

/** A display value a screener may store (`[columns]` or a criterion id), shown when present. */
interface MetricColumn {
  key: string;
  header: string;
  description: string;
  format: ValueFormat;
}

const METRIC_COLUMNS: readonly MetricColumn[] = [
  {
    key: 'hv30',
    header: 'HV30',
    description: '30-day historical volatility',
    format: { kind: 'percent' },
  },
  {
    key: 'iv_hv_ratio',
    header: 'IV / HV',
    description: 'IV30 over HV30',
    format: { kind: 'number', digits: 2 },
  },
  {
    key: 'put_strike',
    header: 'Put strike',
    description: 'Best put: strike',
    format: { kind: 'currency' },
  },
  {
    key: 'put_delta',
    header: 'Put delta',
    description: 'Best put: delta',
    format: { kind: 'number', digits: 2 },
  },
  {
    key: 'put_premium',
    header: 'Put premium',
    description: 'Best put: premium',
    format: { kind: 'currency' },
  },
  {
    key: 'put_roc',
    header: 'Put ROC',
    description: 'Best put: return on capital',
    format: { kind: 'percent' },
  },
];

/** A tooltip only when there is something to say (props are exact: no `title: undefined`). */
const titled = (title: string | undefined) => (title === undefined ? {} : { title });

/** The one display-column rule: a column is shown when some idea has a value for it. */
export function anyValue(ideas: readonly Idea[], value: (idea: Idea) => unknown): boolean {
  return ideas.some((idea) => value(idea) !== null && value(idea) !== undefined);
}

const numeric = (idea: Idea, key: string): number | null => {
  const value = idea.metrics[key];
  return typeof value === 'number' ? value : null;
};

function metricColumns(ideas: readonly Idea[]): DataTableColumn<Idea>[] {
  return METRIC_COLUMNS.filter((m) => anyValue(ideas, (idea) => numeric(idea, m.key))).map((m) => ({
    id: m.key,
    header: m.header,
    description: m.description,
    value: (idea) => numeric(idea, m.key),
    format: m.format,
  }));
}

/** IV30 as the server formats it (`info.format` of the first idea that has one). */
function ivColumns(ideas: readonly Idea[]): DataTableColumn<Idea>[] {
  const served = ideas.map((idea) => factOf(idea, IDEA_FACTS.iv30)).find((v) => v?.info);
  if (!served || !anyValue(ideas, iv30)) return [];
  return [
    {
      id: 'iv30',
      header: 'IV30',
      description: "30-day implied volatility (the VRP gate's: the lower of IBKR's and Cboe's)",
      value: iv30,
      format: valueFormat(served.info),
    },
  ];
}

const earningsColumn: DataTableColumn<Idea> = {
  id: 'earnings',
  header: 'Earnings',
  description: 'The next earnings date; muted: none scheduled, when the last one was',
  value: nextEarnings,
  format: { kind: 'date', style: 'weekday' },
  cell: ({ row }) => {
    const shown = earningsCell(row);
    return (
      <Text size="sm" tone={shown.muted ? 'muted' : 'default'} {...titled(shown.title)}>
        {shown.text}
      </Text>
    );
  },
};

const dteColumn: DataTableColumn<Idea> = {
  id: 'dte',
  header: 'Expiry DTE',
  description:
    'Calendar days to the nearest listed expiry; flagged when earnings come on or before it',
  value: expiryDte,
  format: { kind: 'number' },
  width: 'md',
  cell: ({ row, formatted }) =>
    earningsBeforeExpiry(row) ? (
      <Stack direction="row" gap={2} align="center" justify="end">
        <StatusBadge tone="warning" icon="alert" title="Earnings fall on or before this expiry">
          Earnings first
        </StatusBadge>
        <Mono>{formatted.text}</Mono>
      </Stack>
    ) : (
      <Mono tone={expiryDte(row) === null ? 'muted' : 'default'} {...titled(dteReason(row))}>
        {formatted.text}
      </Mono>
    ),
};

const watchOutColumn: DataTableColumn<Idea> = {
  id: 'watch-out',
  header: 'Watch out',
  description: 'Leveraged / inverse, large move, liquidity risk, earnings before expiry',
  value: (idea) => idea.watchOut.length,
  width: 'lg',
  grow: true,
  cell: ({ row }) => (
    <Stack direction="row" gap={1} wrap>
      {row.watchOut.map((w) => (
        <StatusBadge key={w.id} tone="warning">
          {w.label}
        </StatusBadge>
      ))}
    </Stack>
  ),
};

/** The screeners that picked the ticker, each a button to that screener's results. */
const screenersColumn = (onOpenScreener: (screenerId: string) => void): DataTableColumn<Idea> => ({
  id: 'screeners',
  header: 'Screeners',
  description:
    "Every screener that picked the ticker, highest priority first; each opens that screener's results",
  value: (idea) => idea.picks.length,
  width: 'lg',
  grow: true,
  cell: ({ row }) => (
    <Stack direction="row" gap={1} wrap>
      {row.picks.map((pick) => (
        <Button
          key={pick.screenerId}
          size="sm"
          onClick={() => {
            onOpenScreener(pick.screenerId);
          }}
        >
          {pick.screenerName}
        </Button>
      ))}
    </Stack>
  ),
});

const FRONT: DataTableColumn<Idea>[] = [
  {
    id: 'rank',
    header: '#',
    description: 'Rank: your screener priority, then score',
    value: (idea) => idea.rank,
    format: { kind: 'number' },
    width: 'xs',
    hideable: false,
  },
  {
    id: 'symbol',
    header: 'Ticker',
    value: (idea) => idea.symbol ?? idea.instrumentId,
    mono: true,
    hideable: false,
  },
];

const DECISION: DataTableColumn<Idea>[] = [
  {
    id: 'decision',
    header: 'Decision',
    description: 'The best decision across the screeners that picked it',
    value: (idea) => idea.best.decision,
    cell: ({ row }) => <DecisionBadge decision={row.best.decision} />,
  },
  {
    id: 'score',
    header: 'Score',
    description: 'Score from the screener behind the best decision',
    value: (idea) => idea.best.score,
    format: { kind: 'number', digits: 0 },
  },
];

/** The columns for these ideas (the IV and display-value columns depend on what is served). */
export function ideaColumns(
  ideas: readonly Idea[],
  onOpenScreener: (screenerId: string) => void,
): DataTableColumn<Idea>[] {
  return [
    ...FRONT,
    screenersColumn(onOpenScreener),
    ...DECISION,
    earningsColumn,
    dteColumn,
    ...ivColumns(ideas),
    ...metricColumns(ideas),
    watchOutColumn,
  ];
}
