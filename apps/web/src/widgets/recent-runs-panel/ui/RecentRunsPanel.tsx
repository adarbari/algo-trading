/**
 * Recent nightly runs, one expandable row each (session, status, steps complete, duration); the
 * open row (one at a time, the newest first) shows the run's problems and its timing in one
 * list: the steps this attempt ran (accent bars, duration and share of its work, longest first),
 * then those it reused from an earlier attempt (series bars at the duration they took there,
 * with that attempt's start time).
 */
import {
  BarList,
  Button,
  ExpandableRow,
  EmptyState,
  ErrorState,
  formatValue,
  Legend,
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
  isReused,
  RunStatusBadge,
  stepTimings,
  useNightlyRuns,
  type NightlyRun,
  type StepTiming,
} from '@/entities/run';

const started = (run: NightlyRun) => `${run.startedAt.replace('T', ' ').slice(0, 16)} UTC`;

const DONE = new Set(['COMPLETE', 'SUCCEEDED']);

const clock = (iso: string | null) => (iso === null ? '' : `${iso.slice(11, 16)} UTC`);

function display(t: StepTiming): string {
  if (!isReused(t)) {
    return `${formatDuration(t.durationS)} · ${formatValue(t.share, { kind: 'percent', digits: 0 }).text}`;
  }
  const there = t.originDurationS === null ? '' : ` · ${formatDuration(t.originDurationS)}`;
  const at = t.originStartedAt === null ? '' : ` · ${clock(t.originStartedAt)}`;
  return `reused${at}${there}`;
}

function toneOf(t: StepTiming) {
  const status = t.status.toUpperCase();
  if (status === 'FAILED') return 'negative';
  if (!DONE.has(status)) return 'warning';
  return isReused(t) ? 's2' : 'accent';
}

function RunTiming({ run }: { run: NightlyRun }) {
  const timings = stepTimings(run);
  const reused = timings.filter(isReused).length;
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
      {reused > 0 && (
        <Legend
          label="Step bar colours"
          items={[
            { id: 'ran', label: 'Ran now', tone: 'accent', value: timings.length - reused },
            { id: 'reused', label: 'Reused from earlier', tone: 's2', value: reused },
          ]}
        />
      )}
      <BarList
        label={`Step durations of the run started ${started(run)}`}
        items={timings.map((t) => ({
          id: t.name,
          label: t.name,
          value: isReused(t) ? (t.originDurationS ?? 0) : t.durationS,
          display: display(t),
          tone: toneOf(t),
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
