/**
 * The Admin › Evaluations headline: the StatStrip over the stored edge evaluation runs (runs in
 * the 7 days up to the newest run and how many failed, the latest run, runs still going, exploratory runs that
 * never count toward a site verdict). Counted from the same list the runs table shows.
 */
import { formatValue, StatStrip, type StatItem } from '@algotrade/ui';

import { stamp, useHarnessRuns, type HarnessRun } from '@/entities/harness-run';

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const count = (n: number) => formatValue(n, { kind: 'number' }).text;

export function summaryItems(runs: readonly HarnessRun[]): StatItem[] {
  // The window ends at the newest run (the browser clock is not the data's session).
  const [latest] = runs;
  const end = latest ? Date.parse(latest.startedAt) : 0;
  const recent = runs.filter((r) => end - Date.parse(r.startedAt) <= WEEK_MS);
  const failed = recent.filter((r) => r.status === 'failed').length;
  const running = runs.filter((r) => r.status === 'running').length;
  const exploratory = recent.filter((r) => r.exploratory).length;
  return [
    {
      id: 'recent',
      label: 'Runs, 7 days to the latest',
      value: count(recent.length),
      tone: failed ? 'warning' : 'default',
      sub: `${count(failed)} failed`,
    },
    {
      id: 'latest',
      label: 'Latest run',
      value: latest ? latest.status : '—',
      sub: latest ? `${latest.edgeId} · ${stamp(latest.startedAt)}` : 'no run recorded',
    },
    { id: 'running', label: 'Running now', value: count(running) },
    {
      id: 'exploratory',
      label: 'Exploratory, same 7 days',
      value: count(exploratory),
      sub: 'own split, never toward a site verdict',
    },
  ];
}

export function HarnessRunSummary() {
  const runs = useHarnessRuns();
  return (
    <StatStrip
      label="Evaluation runs summary"
      loading={runs.isPending}
      error={runs.isError && !runs.data ? 'The summary failed to load.' : undefined}
      items={summaryItems(runs.data ?? [])}
    />
  );
}
