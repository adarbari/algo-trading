/**
 * The screener runs' columns: one run per row (not instruments x features), with what it
 * picked and recorded. A figure the run did not record is empty, never zero. The phone shows
 * the session, the screener and the status.
 */
import { Mono, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import { stamp, statusText, statusTone, type ScreenerRunSummary } from '@/entities/screener-run';
import { termHelp } from '@/features/guide-help';

const COUNT = { kind: 'number' } as const;

export function runColumns(): DataTableColumn<ScreenerRunSummary>[] {
  return [
    {
      id: 'session',
      header: 'Session',
      headerAction: termHelp('session'),
      value: (r) => r.session,
      cell: ({ row }) => <Mono size="sm">{row.session}</Mono>,
      hideable: false,
      essential: true,
    },
    {
      id: 'screener',
      header: 'Screener',
      headerAction: termHelp('screener'),
      value: (r) => r.configId,
      grow: true,
      essential: true,
    },
    {
      id: 'owner',
      header: 'Owner',
      headerAction: termHelp('screener_run_owner'),
      value: (r) => r.owner,
    },
    {
      id: 'status',
      header: 'Status',
      headerAction: termHelp('screener_run_status'),
      value: (r) => statusText(r.status),
      essential: true,
      cell: ({ row }) => (
        <StatusBadge tone={statusTone(row.status)}>{statusText(row.status)}</StatusBadge>
      ),
    },
    {
      id: 'picked',
      header: 'Picked',
      headerAction: termHelp('screener_run_picked'),
      value: (r) => r.picked ?? null,
      format: COUNT,
      align: 'end',
    },
    {
      id: 'paused',
      header: 'Paused',
      headerAction: termHelp('paused'),
      value: (r) => r.paused ?? null,
      format: COUNT,
      align: 'end',
    },
    {
      id: 'regime',
      header: 'Regime',
      headerAction: termHelp('regime'),
      value: (r) => r.regime ?? null,
    },
    {
      id: 'coverage',
      header: 'Coverage',
      headerAction: termHelp('screener_run_coverage'),
      value: (r) => r.coverage ?? null,
    },
    {
      id: 'started',
      header: 'Started',
      headerAction: termHelp('screener_run_started'),
      value: (r) => r.startedAt,
      cell: ({ row }) => <Mono size="sm">{stamp(row.startedAt)}</Mono>,
    },
  ];
}
