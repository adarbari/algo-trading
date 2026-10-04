/**
 * Events: the focused ticker's earnings, dividends, splits and ticker / reference changes in
 * one timeline, newest first (upcoming earnings included).
 */
import {
  DataTable,
  Panel,
  StatusBadge,
  type DataTableColumn,
  type StatusTone,
} from '@algotrade/ui';
import { useMemo } from 'react';

import {
  toTimeline,
  useInstrumentEvents,
  type EventKind,
  type TimelineEvent,
} from '@/entities/instrument';

const TONES: Readonly<Record<EventKind, StatusTone>> = {
  earnings: 'info',
  dividend: 'positive',
  split: 'warning',
  change: 'neutral',
  other: 'neutral',
};

const COLUMNS: readonly DataTableColumn<TimelineEvent>[] = [
  {
    id: 'date',
    header: 'Date',
    value: (e) => e.date,
    format: { kind: 'date' },
    width: 'sm',
  },
  {
    id: 'kind',
    header: 'Event',
    value: (e) => e.label,
    width: 'md',
    cell: ({ row }) => <StatusBadge tone={TONES[row.kind]}>{row.label}</StatusBadge>,
  },
  { id: 'detail', header: 'Detail', value: (e) => e.detail, grow: true, tone: 'secondary' },
];

export interface EventsPanelProps {
  symbol: string;
}

export function EventsPanel({ symbol }: EventsPanelProps) {
  const events = useInstrumentEvents(symbol);
  const rows = useMemo(() => toTimeline(events.data ?? []), [events.data]);
  return (
    <Panel
      title={`${symbol} · events`}
      description="Earnings, dividends, splits, ticker and index changes"
      flush
      state={events.isError ? 'error' : 'ready'}
      errorMessage={`${symbol} events failed to load.`}
      onRetry={() => void events.refetch()}
    >
      <DataTable<TimelineEvent>
        label={`${symbol} events`}
        columns={COLUMNS}
        rows={rows}
        getRowId={(e) => e.id}
        defaultSort={{ columnId: 'date', direction: 'desc' }}
        visibleRows={14}
        status={events.isPending ? 'loading' : 'ready'}
        emptyMessage={`No stored events for ${symbol}.`}
      />
    </Panel>
  );
}
