/** The latest data-quality checks (PASS / WARN / FAIL) with what each measured, in a table. */
import {
  DataTable,
  EmptyState,
  ErrorState,
  formatValue,
  Panel,
  Skeleton,
  type DataTableColumn,
} from '@algotrade/ui';

import { ApiError } from '@/shared/api';
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
  const report = quality.data;
  const title = report
    ? `Quality checks · ${formatValue(report.session, { kind: 'date', style: 'weekday' }).text}`
    : 'Quality checks';
  const missing = quality.error instanceof ApiError && quality.error.status === 404;
  return (
    <Panel
      title={title}
      description={report && `run ${report.status}`}
      actions={report && <RunStatusBadge status={report.status} />}
      flush={Boolean(report)}
    >
      {quality.isPending ? (
        <Skeleton variant="table" rows={5} columns={3} label="Loading quality checks…" />
      ) : missing ? (
        <EmptyState
          compact
          title="No quality checks yet"
          description="The nightly run records them after ingesting a session."
        />
      ) : quality.isError ? (
        <ErrorState
          compact
          title="Quality checks could not load."
          detail={quality.error.message}
          onRetry={() => void quality.refetch()}
          retrying={quality.isFetching}
        />
      ) : (
        <DataTable
          label="Quality checks"
          columns={COLUMNS}
          rows={report?.checks ?? []}
          getRowId={(c) => c.name}
          defaultSort={{ columnId: 'status', direction: 'asc' }}
          visibleRows={Math.max(report?.checks.length ?? 0, 3)}
          emptyMessage="The run recorded no checks."
        />
      )}
    </Panel>
  );
}
