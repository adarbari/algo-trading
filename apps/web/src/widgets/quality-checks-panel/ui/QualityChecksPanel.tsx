/**
 * The latest session's data-quality checks (PASS / WARN / FAIL) with what each measured, in a
 * table; the session's NOT_RUN reason when it has no data-quality run.
 */
import {
  DataTable,
  EmptyState,
  ErrorState,
  formatValue,
  Panel,
  Skeleton,
  type DataTableColumn,
} from '@algotrade/ui';

import { RunStatusBadge, useQualityChecks, type QualityCheck } from '@/entities/run';

const RANK: Record<string, number> = { FAIL: 0, WARN: 1, PASS: 2 };

const COLUMNS: DataTableColumn<QualityCheck>[] = [
  { id: 'name', header: 'Check', value: (c) => c.name, mono: true, width: 'lg' },
  {
    id: 'status',
    header: 'Result',
    description: 'PASS, WARN or FAIL; any FAIL makes the nightly run partial',
    value: (c) => RANK[c.status] ?? 3,
    cell: ({ row }) => <RunStatusBadge status={row.status} />,
    width: 'sm',
  },
  {
    id: 'detail',
    header: 'Measured, against the rule',
    value: (c) => c.detail,
    tone: 'secondary',
    grow: true,
    sortable: false,
  },
];

export function QualityChecksPanel() {
  const quality = useQualityChecks();
  const served = quality.data;
  const report = served && !served.unknown ? served : null;
  const title = served
    ? `Quality checks · ${formatValue(served.session, { kind: 'date', style: 'weekday' }).text}`
    : 'Quality checks';
  return (
    <Panel
      title={title}
      description={report?.status ? `run ${report.status}` : undefined}
      actions={report?.status && <RunStatusBadge status={report.status} />}
      flush={Boolean(report)}
    >
      {quality.isPending ? (
        <Skeleton variant="table" rows={5} columns={3} label="Loading quality checks…" />
      ) : quality.isError ? (
        <ErrorState
          compact
          title="Quality checks could not load."
          detail={quality.error.message}
          onRetry={() => void quality.refetch()}
          retrying={quality.isFetching}
        />
      ) : !report ? (
        <EmptyState
          compact
          title="No quality checks for this session"
          description={
            served?.unknown
              ? `${served.unknown.detail}. The nightly run records them after ingesting a session.`
              : 'The nightly run records them after ingesting a session.'
          }
        />
      ) : (
        <DataTable
          label="Quality checks"
          columns={COLUMNS}
          rows={report.checks}
          getRowId={(c) => c.name}
          defaultSort={{ columnId: 'status', direction: 'asc' }}
          visibleRows={Math.max(report.checks.length, 3)}
          emptyMessage="The run recorded no checks."
        />
      )}
    </Panel>
  );
}
