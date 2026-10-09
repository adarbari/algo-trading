/**
 * The harness runs' columns: one evaluation run per row (not instruments x features), with what
 * it measured and what it left out. A figure the run did not record is empty, never zero. The
 * phone shows the edge, the status and when it started.
 */
import { Mono, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import { rangeText, stamp, statusTone, type HarnessRun } from '@/entities/harness-run';
import { GuideHelp } from '@/features/guide-help';

const term = (id: string) => <GuideHelp entry={{ kind: 'term', id }} />;
const COUNT = { kind: 'number' } as const;

export function runColumns(): DataTableColumn<HarnessRun>[] {
  return [
    {
      id: 'edge',
      header: 'Edge',
      value: (r) => r.edgeId,
      hideable: false,
      grow: true,
      essential: true,
    },
    { id: 'user', header: 'User', value: (r) => r.user },
    {
      id: 'run',
      header: 'Run',
      value: (r) => r.runId,
      cell: ({ row }) => <Mono size="sm">{row.runId}</Mono>,
    },
    {
      id: 'started',
      header: 'Started',
      value: (r) => r.startedAt,
      cell: ({ row }) => <Mono size="sm">{stamp(row.startedAt)}</Mono>,
      essential: true,
    },
    {
      id: 'finished',
      header: 'Finished',
      value: (r) => r.finishedAt ?? null,
      cell: ({ row }) => (
        <Mono size="sm" tone={row.finishedAt ? 'default' : 'muted'}>
          {row.finishedAt ? stamp(row.finishedAt) : '—'}
        </Mono>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      value: (r) => r.status,
      essential: true,
      cell: ({ row }) => <StatusBadge tone={statusTone(row.status)}>{row.status}</StatusBadge>,
    },
    {
      id: 'range',
      header: 'Range',
      value: (r) => rangeText(r.rangeFrom, r.rangeTo),
      tone: 'secondary',
    },
    {
      id: 'split',
      header: 'Split from',
      headerAction: term('out_of_sample'),
      value: (r) => r.splitFrom ?? null,
      cell: ({ row }) => (
        <>
          <Mono size="sm">{row.splitFrom ?? 'none'}</Mono>
          {row.exploratory && <StatusBadge tone="warning">EXPLORATORY</StatusBadge>}
        </>
      ),
    },
    { id: 'variants', header: 'Variants', value: (r) => r.variants.join(', '), mono: true },
    { id: 'horizons', header: 'Holding periods', value: (r) => r.horizons.join(', '), mono: true },
    {
      id: 'sessions',
      header: 'Trades',
      value: (r) => r.sessions ?? null,
      format: COUNT,
      align: 'end',
    },
    {
      id: 'unclosed',
      header: 'Unclosed',
      headerAction: term('harness_exclusions'),
      value: (r) => r.unclosed ?? null,
      format: COUNT,
      align: 'end',
    },
    {
      id: 'coverage',
      header: 'Coverage',
      headerAction: term('harness_exclusions'),
      value: (r) => r.excludedCoverage ?? null,
      format: COUNT,
      align: 'end',
    },
    {
      id: 'score',
      header: 'Score coverage',
      headerAction: term('harness_exclusions'),
      value: (r) => r.scoreCoverage ?? null,
      format: { kind: 'percent', digits: 0 },
      align: 'end',
    },
    {
      id: 'noEntry',
      header: 'No entry bar',
      headerAction: term('harness_exclusions'),
      value: (r) => r.noEntryBar ?? null,
      format: COUNT,
      align: 'end',
    },
    {
      id: 'trials',
      header: 'Variants tried',
      headerAction: term('variants_tried'),
      value: (r) => r.trials ?? null,
      format: COUNT,
      align: 'end',
    },
    {
      id: 'knowledge',
      header: 'Knowledge ts',
      headerAction: term('knowledge_time'),
      value: (r) => r.knowledgeTs,
      cell: ({ row }) => <Mono size="sm">{stamp(row.knowledgeTs)}</Mono>,
    },
  ];
}
