/**
 * The scope list's columns: one scoped name per row, in the server's list order. The share of big
 * moves and the review date come from the server; a name with none shows a dash, never a guess.
 * A stale name has a badge beside its date. The phone shows the ticker, the stale flag and the
 * remove action.
 */
import { Button, Mono, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import {
  addedBy,
  reasonLabel,
  sourceLabel,
  TERM_OF_LAST_REVIEW,
  TERM_OF_MOVES,
  TERM_OF_REASONS,
  TERM_OF_SCOPE_NAME,
  TERM_OF_SOURCE,
  TERM_OF_STALE,
  type ScopeName,
} from '@/entities/event-scope';
import { termHelp } from '@/features/guide-help';

const dash = (
  <Mono size="sm" tone="muted">
    —
  </Mono>
);

export function scopeColumns(onRemove: (symbol: string) => void): DataTableColumn<ScopeName>[] {
  return [
    {
      id: 'symbol',
      header: 'Ticker',
      headerAction: termHelp(TERM_OF_SCOPE_NAME),
      value: (n) => n.symbol,
      mono: true,
      hideable: false,
      essential: true,
    },
    {
      id: 'reasons',
      header: 'Why in scope',
      headerAction: termHelp(TERM_OF_REASONS),
      value: (n) => n.reasons.map(reasonLabel).join(', '),
      grow: true,
      tone: 'secondary',
    },
    {
      id: 'source',
      header: 'Source',
      headerAction: termHelp(TERM_OF_SOURCE),
      value: (n) => n.source,
      cell: ({ row }) => (
        <>
          {sourceLabel(row.source)}
          {addedBy(row) && (
            <Mono size="sm" tone="muted">
              {' '}
              {addedBy(row)}
            </Mono>
          )}
        </>
      ),
    },
    {
      id: 'added',
      header: 'Added',
      value: (n) => n.addedOn,
      cell: ({ row }) => <Mono size="sm">{row.addedOn}</Mono>,
    },
    {
      id: 'review',
      header: 'Last review',
      headerAction: termHelp(TERM_OF_LAST_REVIEW),
      value: (n) => n.lastReview ?? null,
      cell: ({ row }) => (row.lastReview ? <Mono size="sm">{row.lastReview}</Mono> : dash),
    },
    {
      id: 'stale',
      header: 'Review status',
      headerAction: termHelp(TERM_OF_STALE),
      value: (n) => n.stale,
      essential: true,
      cell: ({ row }) =>
        row.stale ? (
          <StatusBadge tone="warning">STALE</StatusBadge>
        ) : (
          <StatusBadge>CURRENT</StatusBadge>
        ),
    },
    {
      id: 'moves',
      header: 'Big moves attributed',
      headerAction: termHelp(TERM_OF_MOVES),
      value: (n) => n.moves?.share ?? null,
      format: { kind: 'percent', digits: 0 },
      align: 'end',
    },
    {
      id: 'note',
      header: 'Note',
      value: (n) => n.note || null,
      tone: 'secondary',
    },
    {
      id: 'remove',
      header: 'Remove',
      value: (n) => n.symbol,
      sortable: false,
      hideable: false,
      essential: true,
      cell: ({ row }) => (
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Remove ${row.symbol}`}
          onClick={() => {
            onRemove(row.symbol);
          }}
        >
          Remove
        </Button>
      ),
    },
  ];
}
