/**
 * The edges list's columns: name, status (its Guide button), frozen period (its Guide button)
 * and the canonical run's id (or that there is none). The rows are edge documents, not
 * instruments.
 */
import { Mono, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import { statusLabel, statusTone, type Edge } from '@/entities/edge';
import { GuideHelp } from '@/features/guide-help';

export function edgeColumns(): DataTableColumn<Edge>[] {
  return [
    {
      id: 'name',
      header: 'Edge',
      value: (e) => e.name,
      hideable: false,
      grow: true,
      essential: true,
    },
    {
      id: 'status',
      header: 'Status',
      headerAction: <GuideHelp entry={{ kind: 'term', id: 'edge_status' }} />,
      value: (e) => e.status,
      essential: true,
      cell: ({ row }) => (
        <StatusBadge tone={statusTone(row.status)}>{statusLabel(row.status)}</StatusBadge>
      ),
    },
    {
      id: 'frozen',
      header: 'Frozen from',
      headerAction: <GuideHelp entry={{ kind: 'term', id: 'frozen_period' }} />,
      value: (e) => e.frozenFrom ?? null,
      format: { kind: 'date', style: 'iso' },
      align: 'start',
      tone: 'secondary',
    },
    {
      id: 'run',
      header: 'Canonical run',
      value: (e) => e.canonicalRun?.runId ?? null,
      tone: 'secondary',
      cell: ({ row }) =>
        row.canonicalRun ? (
          <Mono size="sm">{row.canonicalRun.runId}</Mono>
        ) : (
          <Mono size="sm" tone="muted">
            none
          </Mono>
        ),
    },
  ];
}
