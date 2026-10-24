/**
 * Under a screener page's title: the last run in one line (its session, state, version, picks,
 * what is new and dropped since the run before, and what it left out) and a strip of the last
 * sessions, one square each (ran, partial, not run) with a label on hover or tap. A session that
 * did not run says so in the server's public words and, for the session the page shows, offers
 * "Run now" (the on-request run, ADR 0033). An admin also gets the cause chain the server sent
 * only to them and a way to the run in Screener runs. Every word that needs explaining opens
 * its Guide entry; the server decided every state and count.
 */
import { Button, SessionStrip, Stack, StatusBadge, Text, TextLink } from '@algotrade/ui';

import { UnavailableNote, UnknownNote, type ServedUnavailable } from '@/entities/availability';
import { featureTitle } from '@/entities/feature';
import { runMessage, useRunScreener, type RecentRun } from '@/entities/screen';
import { useViewer } from '@/entities/viewer';
import { termHelp } from '@/features/guide-help';

import { runLineParts, stripItems } from '../model/recent-runs';

export interface ScreenerRunLineProps {
  /** The screener shown (its on-request run). */
  id: string;
  /** Its recent runs, oldest first, the last the page's own session. */
  runs: readonly RecentRun[];
  /** What the served run left out (the page's `latestRun.unavailable`). */
  gaps?: readonly ServedUnavailable[];
}

const TONE = { COMPLETE: 'positive', PARTIAL: 'warning', NOT_RUN: 'neutral' } as const;
const STATE = { COMPLETE: 'Complete', PARTIAL: 'Partial', NOT_RUN: 'Not run' } as const;

export function ScreenerRunLine({ id, runs, gaps = [] }: ScreenerRunLineProps) {
  const runner = useRunScreener(id);
  const admin = useViewer().data?.role === 'admin';
  const shown = runs.find((run) => run.served) ?? runs.at(-1);
  if (!shown) return null;
  const parts = runLineParts(shown);
  const ranHere = shown.state !== 'NOT_RUN';
  const facts = [parts.version, parts.picked, parts.changes, parts.leftOut]
    .filter((f) => f !== null)
    .join(' · ');
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={2} align="center" wrap>
        <Text size="sm" tone="secondary">{`Run ${parts.session}`}</Text>
        <StatusBadge tone={TONE[shown.state]}>{STATE[shown.state]}</StatusBadge>
        {termHelp('run_state')}
        {facts ? (
          <Text size="sm" tone="secondary" numeric>
            {facts}
          </Text>
        ) : null}
        {ranHere && admin && shown.runId !== null ? (
          <TextLink size="sm" href={`/admin/screener-runs?run=${encodeURIComponent(shown.runId)}`}>
            Open in Screener runs
          </TextLink>
        ) : null}
      </Stack>
      {ranHere ? <UnavailableNote gaps={gaps} titleOf={featureTitle} /> : null}
      {!ranHere && shown.notRun ? <UnknownNote unknown={shown.notRun} /> : null}
      {!ranHere ? (
        <Stack direction="row" gap={2} align="center" wrap>
          <Button size="sm" variant="secondary" loading={runner.running} onClick={runner.start}>
            Run now
          </Button>
          <Text size="sm" tone="muted">
            {runner.error ? 'The run could not be started' : runMessage(runner.run)}
          </Text>
        </Stack>
      ) : null}
      <Stack direction="row" gap={2} align="center">
        <SessionStrip items={stripItems(runs)} label={`Last ${String(runs.length)} sessions`} />
        {termHelp('session_strip')}
      </Stack>
    </Stack>
  );
}
