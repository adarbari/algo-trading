/**
 * A playbook's criteria table: what each criterion asks in plain words, the field it reads (a
 * link to its Guide page), the rule as `op value mode tolerance`, and what a miss does. The rows
 * are the preset's criteria, not instruments.
 */
import { Mono, Text, TextLink, type DataTableColumn } from '@algotrade/ui';

import { fieldPath } from '@/entities/guide';

export interface CriterionRow {
  name: string;
  asks: string | null;
  field: string;
  rule: string;
  mode: string;
  onMiss: string | null;
}

/** What a miss does: a soft criterion's `on_miss`, a hard one rejects, a score one scores. */
export function missText(row: CriterionRow): string {
  if (row.onMiss) return row.onMiss;
  return row.mode === 'hard' ? 'reject' : row.mode;
}

export function criteriaColumns(): DataTableColumn<CriterionRow>[] {
  return [
    {
      id: 'asks',
      header: 'What it asks',
      value: (row) => row.asks ?? row.name,
      width: 'xl',
      grow: true,
      hideable: false,
      sortable: false,
    },
    {
      id: 'field',
      header: 'Field',
      value: (row) => row.field,
      width: 'xl',
      hideable: false,
      sortable: false,
      cell: ({ row }) => (
        <TextLink href={fieldPath(row.field)} mono size="sm">
          {row.field}
        </TextLink>
      ),
    },
    {
      id: 'rule',
      header: 'Rule',
      value: (row) => row.rule,
      width: 'lg',
      hideable: false,
      sortable: false,
      cell: ({ row }) => <Mono size="sm">{row.rule}</Mono>,
    },
    {
      id: 'miss',
      header: 'If missed',
      value: (row) => missText(row),
      hideable: false,
      sortable: false,
      cell: ({ row }) => (
        <Text size="sm" tone={row.onMiss ? 'warning' : 'muted'}>
          {missText(row)}
        </Text>
      ),
    },
  ];
}
