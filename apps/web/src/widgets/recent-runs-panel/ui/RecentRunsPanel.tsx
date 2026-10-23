/**
 * Recent nightly runs, one expandable row each (session, status, steps complete, duration); the
 * open row (one at a time, the newest first) shows the run's problems and its timing in one
 * list, each step in one of five states (ran now, reused from an earlier attempt, waiting on its
 * source, held by an upstream step, failed) with when it began; selecting a step marks what it
 * needs and what it holds back, with its details below.
 */
import {
  BarList,
  Button,
  type DataTone,
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
  neighbours,
  relations,
  RunStatusBadge,
  stepTimings,
  useNightlyRuns,
  type NightlyRun,
  type Relation,
  type StepState,
  type StepTiming,
} from '@/entities/run';

const started = (run: NightlyRun) => `${run.startedAt.replace('T', ' ').slice(0, 16)} UTC`;

const clock = (iso: string | null) => (iso === null ? '' : `${iso.slice(11, 16)} UTC`);
const at = (t: StepTiming) => (t.startedAt === null ? [] : [clock(t.startedAt)]);

function display(t: StepTiming): string {
  const took = formatDuration(t.durationS);
  switch (t.state) {
    case 'ran':
      return [took, formatValue(t.share, { kind: 'percent', digits: 0 }).text, ...at(t)].join(
        ' · ',
      );
    case 'waiting':
    case 'failed':
      return [t.state, took, ...at(t)].join(' · ');
    case 'reused':
      return [
        'reused',
        ...at(t),
        ...(t.originDurationS === null ? [] : [formatDuration(t.originDurationS)]),
      ].join(' · ');
    case 'held':
      return 'not run';
  }
}

const TONES: Record<StepState, DataTone> = {
  ran: 'accent',
  reused: 'muted',
  waiting: 'warning',
  held: 'empty',
  failed: 'negative',
};

const KEY: Record<StepState, string> = {
  failed: 'Failed',
  ran: 'Ran now',
  waiting: 'Waiting on its source',
  reused: 'Reused from earlier',
  held: 'Held by an upstream step',
};

const emphasis = (relation: Relation | undefined) =>
  relation === undefined ? {} : { emphasis: relation };

function list(names: readonly string[]) {
  return names.length === 0 ? 'nothing' : names.join(', ');
}

function StepDetail({ step, timings }: { step: StepTiming; timings: readonly StepTiming[] }) {
  const { needs, holds } = neighbours(timings, step.name);
  const note = step.error ?? step.reason;
  return (
    <Stack gap={1}>
      <Text size="sm">
        <Mono>{step.name}</Mono>
        {` · ${KEY[step.state].toLowerCase()}${note === null ? '' : ` · ${note}`}`}
      </Text>
      <Text size="sm" tone="secondary">
        {needs === null
          ? 'This run did not record its dependencies.'
          : `Needs: ${list(needs)} · Holds back: ${list(holds)}${step.rerunsAfter.length > 0 ? ` · Re-runs after: ${list(step.rerunsAfter)}` : ''}`}
      </Text>
    </Stack>
  );
}

function RunTiming({ run }: { run: NightlyRun }) {
  const timings = stepTimings(run);
  const [selected, setSelected] = useState<string | null>(null);
  const related = relations(timings, selected);
  const present = (Object.keys(KEY) as StepState[]).filter((k) =>
    timings.some((t) => t.state === k),
  );
  const step = timings.find((t) => t.name === selected);
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
      <Legend
        label="Step bar colours"
        items={present.map((k) => ({
          id: k,
          label: KEY[k],
          tone: TONES[k],
          value: timings.filter((t) => t.state === k).length,
        }))}
      />
      <BarList
        label={`Step durations of the run started ${started(run)}`}
        onSelect={(name) => {
          setSelected(selected === name ? null : name);
        }}
        items={timings.map((t) => ({
          id: t.name,
          label: t.name,
          value: t.state === 'reused' ? (t.originDurationS ?? 0) : t.durationS,
          display: display(t),
          tone: TONES[t.state],
          hollow: t.state === 'held',
          ...emphasis(related.get(t.name)),
        }))}
        emptyMessage="This run recorded no steps."
      />
      {step !== undefined && <StepDetail step={step} timings={timings} />}
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
