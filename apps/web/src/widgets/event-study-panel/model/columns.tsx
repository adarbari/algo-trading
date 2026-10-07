/**
 * The columns of the Events tab's two lists: the dated events ahead (an `EventChip` per row)
 * and the 8-K filings. Every cell is the API's text.
 */
import { EventChip, Text, timeText, type DataTableColumn, type EventItem } from '@algotrade/ui';

import type { StudyFiling } from '@/entities/event';

export interface FilingRow {
  id: string;
  filing: StudyFiling;
  item: EventItem;
}

export const AHEAD_COLUMNS: readonly DataTableColumn<EventItem>[] = [
  { id: 'date', header: 'Date', value: (e) => e.date, format: { kind: 'date' }, width: 'sm' },
  {
    id: 'event',
    header: 'Event',
    value: (e) => e.label,
    width: 'md',
    grow: true,
    cell: ({ row }) => <EventChip kind={row.kind} label={row.label} event={row} />,
  },
  { id: 'time', header: 'When', value: (e) => timeText(e.time), width: 'md', tone: 'secondary' },
  { id: 'source', header: 'Source', value: (e) => e.source, width: 'md', tone: 'muted' },
];

export const FILING_COLUMNS: readonly DataTableColumn<FilingRow>[] = [
  {
    id: 'date',
    header: 'Filed',
    value: (r) => r.filing.filingDate,
    format: { kind: 'date' },
    width: 'sm',
  },
  { id: 'form', header: 'Form', value: (r) => r.filing.form, width: 'sm', mono: true },
  {
    id: 'what',
    header: 'What',
    value: (r) => r.filing.label,
    width: 'md',
    grow: true,
    cell: ({ row }) => <EventChip kind="filing" label={row.filing.label} event={row.item} />,
  },
  {
    id: 'items',
    header: 'Items',
    value: (r) => r.filing.items.join(', '),
    width: 'md',
    tone: 'secondary',
    cell: ({ row }) => <Text size="sm">{row.filing.items.join(', ')}</Text>,
  },
];
