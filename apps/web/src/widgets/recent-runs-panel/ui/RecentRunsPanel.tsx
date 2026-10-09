/**
 * Recent nightly runs, one expandable row each (session, status, steps complete, duration); the
 * open row (one at a time, the newest first) shows the run's problems and its timing: each
 * step's duration as a bar with its share of the run, longest first.
 */
import {
  BarList,
  Button,
  ExpandableRow,
  EmptyState,
  ErrorState,
  formatValue,
  Mono,
  Panel,
  Skeleton,
  Stack,
  Text,
  Tooltip,
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

const started = (run: NightlyRun) => `${run.startedAt.replace('T', ' ').slice(0, 16)} UTC`;

function RunTiming({ run }: { run: NightlyRun }) {
  const timings = stepTimings(run);
  return (
    <Stack gap={2}>
      {run.problems.length > 0 && (
        <Text size="sm" tone="secondary">
          {run.problems.join('; ')}
        </Text>
      )}
      <Text size="sm" tone="muted">
        {`Run timing · ${formatValue(run.session, { kind: 'date', style: 'weekday' }).text} · started ${started(run)} · ${formatDuration(run.durationS)}`}
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
  // undefined: the newest run is open; null: the user closed it.
  const [chosen, setChosen] = useState<string | null | undefined>(undefined);
  const openId = chosen === undefined ? runs.data?.[0]?.runId : chosen;
  return (
    <Panel
      title="Recent nightly runs"
      description="open a run to see its timing"
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
        <Stack gap={0} as="ul" aria-label="Recent nightly runs">
          {runs.data.map((run) => (
            <Stack as="li" key={run.runId} gap={0}>
              <ExpandableRow
                title={
                  <>
                    {formatValue(run.session, { kind: 'date', style: 'weekday' }).text}{' '}
                    <Mono>{started(run)}</Mono>
                  </>
                }
                badge={<RunStatusBadge status={run.status} />}
                secondary={
                  <Text size="sm" tone="secondary">
                    {`${String(run.steps.length - incompleteSteps(run).length)} of ${String(run.steps.length)} steps complete`}
                  </Text>
                }
                essential={<Mono>{formatDuration(run.durationS)}</Mono>}
                open={openId === run.runId}
                onOpenChange={(open) => {
                  setChosen(open ? run.runId : null);
                }}
              >
                <RunTiming run={run} />
              </ExpandableRow>
            </Stack>
          ))}
        </Stack>
      )}
    </Panel>
  );
}
