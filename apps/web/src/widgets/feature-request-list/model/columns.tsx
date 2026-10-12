/**
 * The feature requests' columns: one requested feature per row (not instruments x features), in
 * the server's ranking. Counts only; a date the request has none for is empty. A promoted row
 * links its site feature to that field's Guide page. The phone shows the rank, the feature and
 * its status.
 */
import { Mono, StatusBadge, TextLink, type DataTableColumn } from '@algotrade/ui';

import { fieldPath } from '@/entities/guide';
import {
  statusLabel,
  statusTone,
  TERM_OF_FEASIBILITY,
  TERM_OF_SCORE,
  TERM_OF_STATUS,
  TERM_OF_UNMAPPED,
  type FeatureRequest,
} from '@/entities/feature-request';
import { termHelp } from '@/features/guide-help';

const COUNT = { kind: 'number' } as const;

export function requestColumns(): DataTableColumn<FeatureRequest>[] {
  return [
    {
      id: 'rank',
      header: 'Rank',
      value: (r) => r.rank,
      format: COUNT,
      align: 'end',
      hideable: false,
      essential: true,
    },
    {
      id: 'ref',
      header: 'Feature',
      value: (r) => r.ref,
      hideable: false,
      essential: true,
      cell: ({ row }) => (
        <>
          <Mono size="sm">{row.ref}</Mono>
          {row.unmapped && <StatusBadge tone="warning">UNMAPPED</StatusBadge>}
        </>
      ),
      headerAction: termHelp(TERM_OF_UNMAPPED),
    },
    {
      id: 'description',
      header: 'Description',
      value: (r) => r.description,
      grow: true,
      tone: 'secondary',
    },
    {
      id: 'feasibility',
      header: 'Feasibility',
      headerAction: termHelp(TERM_OF_FEASIBILITY),
      value: (r) => r.feasibility,
      mono: true,
    },
    {
      id: 'score',
      header: 'Score',
      headerAction: termHelp(TERM_OF_SCORE),
      value: (r) => r.score,
      format: { kind: 'number', digits: 2 },
      align: 'end',
    },
    { id: 'users', header: 'Users', value: (r) => r.users, format: COUNT, align: 'end' },
    { id: 'asked', header: 'Times asked', value: (r) => r.timesAsked, format: COUNT, align: 'end' },
    {
      id: 'first',
      header: 'First seen',
      value: (r) => r.firstSeen ?? null,
      cell: ({ row }) => (
        <Mono size="sm" tone={row.firstSeen ? 'default' : 'muted'}>
          {row.firstSeen ?? '—'}
        </Mono>
      ),
    },
    {
      id: 'last',
      header: 'Last seen',
      value: (r) => r.lastSeen,
      cell: ({ row }) => <Mono size="sm">{row.lastSeen}</Mono>,
    },
    {
      id: 'status',
      header: 'Status',
      headerAction: termHelp(TERM_OF_STATUS),
      value: (r) => r.status,
      essential: true,
      cell: ({ row }) => (
        <StatusBadge tone={statusTone(row.status)}>{statusLabel(row.status)}</StatusBadge>
      ),
    },
    {
      id: 'promoted',
      header: 'Promoted to',
      value: (r) => r.promotedTo || null,
      cell: ({ row }) =>
        row.promotedTo ? (
          <TextLink href={fieldPath(row.promotedTo)} mono size="sm">
            {row.promotedTo}
          </TextLink>
        ) : (
          <Mono size="sm" tone="muted">
            —
          </Mono>
        ),
    },
  ];
}
