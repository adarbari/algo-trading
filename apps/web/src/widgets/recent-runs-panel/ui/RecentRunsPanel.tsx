/**
 * Recent nightly runs (session, start, status, duration, steps, problems) and the timing of the
 * chosen run: each step's duration as a bar with its share of the run, longest first.
 */
import {
  BarList,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  formatValue,
  Panel,
  Skeleton,
  Stack,
  Text,
  Tooltip,
  type DataTableColumn,
} from '@algotrade/ui';
import { useState } from 'react';

import {
  formatDuration,
  incompleteSteps,
  RunStatusBadge,
  stepTimings,
  useNightlyRuns,
  type NightlyRun,
} from '@/entities/run';

const started = (run: NightlyRun) => `${run.started_at.replace('T', ' ').slice(0, 16)} UTC`;

const COLUMNS: DataTableColumn<NightlyRun>[] = [
  {
    id: 'session',
    header: 'Session',
    value: (r) => r.session,
    format: { kind: 'date', style: 'weekday' },
    width: 'sm',
  },
  { id: 'started', header: 'Started', value: started, mono: true, width: 'md' },
  {
    id: 'status',
    header: 'Status',
    value: (r) => r.status,
    cell: ({ row }) => <RunStatusBadge status={row.status} />,
    width: 'sm',
  },
  {
    id: 'duration',
    header: 'Duration',
    value: (r) => r.duration_s,
    cell: ({ row }) => formatDuration(row.duration_s),
    align: 'end',
    width: 'sm',
  },
  {
    id: 'steps',
    header: 'Steps complete',
    value: (r) => r.steps.length - incompleteSteps(r).length,
    cell: ({ row }) =>
      `${String(row.steps.length - incompleteSteps(row).length)} of ${String(row.steps.length)}`,
    align: 'end',
    width: 'sm',
  },
  {
    id: 'problems',
    header: 'Problems',
    value: (r) => r.problems.join('; '),
    tone: 'secondary',
    grow: true,
    sortable: false,
  },
];

function RunTiming({ run }: { run: NightlyRun }) {
  const timings = stepTimings(run);
  return (
    <Stack gap={2}>
      <Text size="sm" tone="muted">
        {`Run timing · ${formatValue(run.session, { kind: 'date', style: 'weekday' }).text} · started ${started(run)} · ${formatDuration(run.duration_s)}`}
      </Text>
      <BarList
        label={`Step durations of the run started ${started(run)}`}
        items={timings.map((t) => ({
          id: t.name,
          label: t.name,
          value: t.durationS,
          display: `${formatDuration(t.durationS)} · ${formatValue(t.share, { kind: 'percent', digits: 0 }).text}`,
          tone:
            t.status.toUpperCase() === 'COMPLETE'
              ? 'accent'
              : t.status.toUpperCase() === 'FAILED'
                ? 'negative'
                : 'warning',
        }))}
        emptyMessage="This run recorded no step durations."
      />
    </Stack>
  );
}

export function RecentRunsPanel() {
  const runs = useNightlyRuns();
  const [chosen, setChosen] = useState<string | null>(null);
  const run = runs.data?.find((r) => r.run_id === chosen) ?? runs.data?.[0];
  return (
    <Panel
      title="Recent nightly runs"
      description="select a run to see its timing"
      actions={
        <Tooltip content="Coming with the jobs API: the API is read-only for now.">
          {(props) => (
            <Button {...props} size="sm" icon="refresh" disabled>
              Re-run nightly
            </Button>
          )}
        </Tooltip>
      }
    >
      {runs.isPending ? (
        <Skeleton variant="table" rows={4} columns={6} label="Loading nightly runs…" />
      ) : runs.isError ? (
        <ErrorState
          compact
          title="Nightly runs could not load."
          detail={runs.error.message}
          onRetry={() => void runs.refetch()}
          retrying={runs.isFetching}
        />
      ) : runs.data.length === 0 ? (
        <EmptyState
          compact
          title="No nightly runs yet"
          description="algotrade-ingest nightly records one per session."
        />
      ) : (
        <Stack gap={4}>
          <DataTable
            label="Recent nightly runs"
            columns={COLUMNS}
            rows={runs.data}
            getRowId={(r) => r.run_id}
            onRowActivate={(r) => {
              setChosen(r.run_id);
            }}
            visibleRows={Math.min(runs.data.length, 10)}
          />
          {run && <RunTiming run={run} />}
        </Stack>
      )}
    </Panel>
  );
}
