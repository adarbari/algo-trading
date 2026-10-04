/**
 * The top-ideas table's columns: rank, ticker, the screeners that picked it (chips, by name),
 * the best decision, score, the screeners' stored display values (IV30, HV30,
 * IV / HV and the best put: a column appears only when some idea has a value for it), next
 * earnings, the closest expiry in days (flagged when earnings come first) and the watch-outs.
 */
import {
  Chip,
  Mono,
  Stack,
  StatusBadge,
  type DataTableColumn,
  type ValueFormat,
} from '@algotrade/ui';

import { DecisionBadge, type Idea } from '@/entities/idea';

/** A display value a screener may store (`[columns]` or a criterion id), shown when present. */
interface MetricColumn {
  key: string;
  header: string;
  description: string;
  format: ValueFormat;
}

const METRIC_COLUMNS: readonly MetricColumn[] = [
  {
    key: 'iv30',
    header: 'IV30',
    description: '30-day implied volatility',
    format: { kind: 'percent' },
  },
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

const numeric = (idea: Idea, key: string): number | null => {
  const value = idea.metrics[key];
  return typeof value === 'number' ? value : null;
};

function metricColumns(ideas: readonly Idea[]): DataTableColumn<Idea>[] {
  return METRIC_COLUMNS.filter((m) => ideas.some((idea) => numeric(idea, m.key) !== null)).map(
    (m) => ({
      id: m.key,
      header: m.header,
      description: m.description,
      value: (idea) => numeric(idea, m.key),
      format: m.format,
    }),
  );
}

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

/** The columns for these ideas (the display-value columns depend on what screeners stored). */
export function ideaColumns(ideas: readonly Idea[]): DataTableColumn<Idea>[] {
  const [front, back] = [BASE.slice(0, 6), BASE.slice(6)];
  return [...front, ...metricColumns(ideas), ...back, watchOutColumn];
}

const BASE: DataTableColumn<Idea>[] = [
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
  {
    id: 'screeners',
    header: 'Screeners',
    description: 'Every screener that picked the ticker, highest priority first',
    value: (idea) => idea.picks.length,
    width: 'lg',
    grow: true,
    cell: ({ row }) => (
      <Stack direction="row" gap={1} wrap>
        {row.picks.map((pick) => (
          <Chip key={pick.screenerId} label={pick.screenerName} />
        ))}
      </Stack>
    ),
  },
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
  {
    id: 'earnings',
    header: 'Earnings',
    description: 'The next earnings date',
    value: (idea) => idea.nextEarningsDate,
    format: { kind: 'date', style: 'weekday' },
  },
  {
    id: 'dte',
    header: 'Expiry DTE',
    description: 'Days to the closest listed expiry; flagged when earnings come on or before it',
    value: (idea) => idea.closestExpiryDte,
    format: { kind: 'number' },
    width: 'md',
    cell: ({ row, formatted }) =>
      row.earningsBeforeExpiry ? (
        <Stack direction="row" gap={2} align="center" justify="end">
          <StatusBadge tone="warning" icon="alert" title="Earnings fall on or before this expiry">
            Earnings first
          </StatusBadge>
          <Mono>{formatted.text}</Mono>
        </Stack>
      ) : (
        <Mono tone={row.closestExpiryDte === null ? 'muted' : 'default'}>{formatted.text}</Mono>
      ),
  },
];
