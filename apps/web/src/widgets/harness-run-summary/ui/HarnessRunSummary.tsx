/**
 * The Admin › Evaluations headline: the StatStrip over the stored edge evaluation runs (runs in
 * the last 7 days and how many failed, the latest run, runs still going, exploratory runs that
 * never count toward a site verdict). Counted from the same list the runs table shows.
 */
import { formatValue, StatStrip, type StatItem } from '@algotrade/ui';

import { useState } from 'react';

import { stamp, useHarnessRuns, type HarnessRun } from '@/entities/harness-run';

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const count = (n: number) => formatValue(n, { kind: 'number' }).text;

export function summaryItems(runs: readonly HarnessRun[], now: number): StatItem[] {
  const recent = runs.filter((r) => now - Date.parse(r.startedAt) <= WEEK_MS);
  const failed = recent.filter((r) => r.status === 'failed').length;
  const running = runs.filter((r) => r.status === 'running').length;
  const exploratory = recent.filter((r) => r.exploratory).length;
  const [latest] = runs;
  return [
    {
      id: 'recent',
      label: 'Runs, last 7 days',
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
      label: 'Exploratory, last 7 days',
      value: count(exploratory),
      sub: 'own split, never toward a site verdict',
    },
  ];
}

export function HarnessRunSummary() {
  const runs = useHarnessRuns();
  const [now] = useState(() => Date.now());
  return (
    <StatStrip
      label="Evaluation runs summary"
      loading={runs.isPending}
      error={runs.isError && !runs.data ? 'The summary failed to load.' : undefined}
      items={summaryItems(runs.data ?? [], now)}
    />
  );
}
