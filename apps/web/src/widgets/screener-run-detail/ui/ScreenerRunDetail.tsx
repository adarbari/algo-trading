/**
 * One screener run's record, beside the runs list (a sheet on a phone): its facts, every
 * decision with its count, what changed against the run before, the gaps it left (an admin also
 * gets the cause chain behind each) and a link to the screener's results. Read-only.
 */
import { EmptyState, Heading, KeyValue, Panel, Stack, TextLink } from '@algotrade/ui';
import { useMemo } from 'react';

import { UnavailableNote } from '@/entities/availability';
import { useScreenerRun } from '@/entities/screener-run';
import { GuideHelp, termHelp } from '@/features/guide-help';

import { changeRows, decisionRows, factRows } from '../model/rows';

const START_PAGE = 'read_screener_runs';

export interface ScreenerRunDetailProps {
  /** The chosen run's id (from the URL), or null. */
  id: string | null;
}

export function ScreenerRunDetail({ id }: ScreenerRunDetailProps) {
  const found = useScreenerRun(id);
  const run = found.data;
  const facts = useMemo(() => (run ? factRows(run) : []), [run]);
  const decisions = useMemo(() => (run ? decisionRows(run) : []), [run]);
  const changes = useMemo(() => (run ? changeRows(run) : []), [run]);
  if (!id) return <EmptyState title="Choose a run" icon="search" bordered />;
  const state =
    found.isError && !run ? 'error' : found.isPending ? 'loading' : run ? 'ready' : 'empty';
  return (
    <Panel
      title={id}
      state={state}
      loadingLabel="Loading the run…"
      emptyMessage="No such run is recorded."
      errorMessage="The run failed to load."
      onRetry={() => void found.refetch()}
      actions={<GuideHelp entry={{ kind: 'start', id: START_PAGE }} />}
    >
      {run && (
        <Stack gap={4}>
          <KeyValue label="Run" items={facts} />
          <Stack gap={2}>
            <Stack direction="row" gap={1} align="center">
              <Heading level={3}>Decisions</Heading>
              {termHelp('screener_run_decisions')}
            </Stack>
            <KeyValue
              label="Decisions"
              items={decisions}
              alignValues="end"
              emptyMessage="Not recorded"
            />
          </Stack>
          <Stack gap={2}>
            <Stack direction="row" gap={1} align="center">
              <Heading level={3}>Changes since the previous run</Heading>
              {termHelp('screener_run_changes')}
            </Stack>
            <KeyValue label="Changes" items={changes} />
          </Stack>
          <UnavailableNote gaps={run.unavailable} />
          <TextLink href={`/test/result/${run.configId}`}>Open the screener's results</TextLink>
        </Stack>
      )}
    </Panel>
  );
}
