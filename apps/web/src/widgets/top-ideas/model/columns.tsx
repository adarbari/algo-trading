/**
 * The top-ideas table's columns: rank, ticker, the screeners that picked it (chips), the best
 * decision, score, tier / class, next earnings, and the closest expiry in days (flagged when
 * earnings come first).
 */
import { Chip, Mono, Stack, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import { DecisionBadge, type Idea } from '@/entities/idea';

export const ideaColumns: DataTableColumn<Idea>[] = [
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
          <Chip key={pick.screenerId} label={pick.screenerId} />
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
    id: 'tier',
    header: 'Tier / class',
    value: (idea) => [idea.best.tier, idea.best.klass].filter(Boolean).join(' / ') || null,
    tone: 'secondary',
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
