/**
 * The Admin › Ingestion headline: a stale-data Banner when the exchange closed a session the
 * store does not have yet, then the StatStrip (completeness of the latest session, quality
 * checks, the latest nightly run's duration, open issues to review).
 */
import { Banner, formatValue, StatStrip, Stack, type StatItem } from '@algotrade/ui';

import { completenessSummary, staleSince, useCompleteness } from '@/entities/ingestion';
import { useFigiReview, useLeveragedReview } from '@/entities/review';
import {
  formatDuration,
  stepTimings,
  useNightlyRuns,
  useQualityChecks,
  type NightlyRun,
  type QualityReport,
} from '@/entities/run';

const weekday = (day: string) => formatValue(day, { kind: 'date', style: 'weekday' }).text;
const count = (n: number) => formatValue(n, { kind: 'number' }).text;
const UNAVAILABLE = 'not available';

function qualityStat(report: QualityReport | null | undefined): StatItem {
  if (!report || report.unknown) {
    return { id: 'quality', label: 'Quality checks', value: '—', sub: UNAVAILABLE };
  }
  const by = (status: string) => report.checks.filter((c) => c.status === status).length;
  const [pass, warn, fail] = [by('PASS'), by('WARN'), by('FAIL')];
  const parts = [
    `${count(pass)} pass`,
    warn && `${count(warn)} warn`,
    fail && `${count(fail)} fail`,
  ];
  const worst =
    report.checks.find((c) => c.status === 'FAIL') ??
    report.checks.find((c) => c.status === 'WARN');
  return {
    id: 'quality',
    label: `Quality checks · ${weekday(report.session)}`,
    value: parts.filter(Boolean).join(' · '),
    tone: fail ? 'negative' : warn ? 'warning' : 'positive',
    sub: worst ? `${worst.name}: ${worst.detail}` : 'every check passes',
  };
}

function runStat(run: NightlyRun | undefined): StatItem {
  if (!run) return { id: 'run', label: 'Nightly run', value: '—', sub: 'no nightly run recorded' };
  const [longest] = stepTimings(run);
  const share = longest ? formatValue(longest.share, { kind: 'percent', digits: 0 }).text : null;
  return {
    id: 'run',
    label: `Nightly run · ${weekday(run.session)}`,
    value: formatDuration(run.durationS),
    tone: run.status === 'complete' ? 'default' : run.status === 'failed' ? 'negative' : 'warning',
    sub: [run.status, longest && `${longest.name} ${share ?? ''} of time`]
      .filter(Boolean)
      .join(' · '),
  };
}

export function IngestionSummary() {
  const completeness = useCompleteness();
  const quality = useQualityChecks();
  const runs = useNightlyRuns();
  const figi = useFigiReview();
  const leveraged = useLeveragedReview();

  const summary = completeness.data ? completenessSummary(completeness.data) : null;
  const stale = completeness.data ? staleSince(completeness.data) : null;
  const figiCount = figi.data?.items.length ?? 0;
  const leveragedCount = leveraged.data?.items.length ?? 0;
  const failedChecks = quality.data?.checks.filter((c) => c.status === 'FAIL').length ?? 0;

  const items: StatItem[] = [
    {
      id: 'completeness',
      label: summary ? `Completeness · ${weekday(summary.session)}` : 'Completeness',
      value: summary?.share ?? null,
      format: { kind: 'percent', digits: 1 },
      tone: summary && summary.failed + summary.partial > 0 ? 'warning' : 'positive',
      sub: summary
        ? [
            `${count(summary.complete)} of ${count(summary.datasets)} datasets complete`,
            summary.partial && `${count(summary.partial)} partial`,
            summary.failed && `${count(summary.failed)} failed`,
          ]
            .filter(Boolean)
            .join(' · ')
        : UNAVAILABLE,
    },
    qualityStat(quality.data),
    runStat(runs.data?.[0]),
    {
      id: 'issues',
      label: 'Open issues',
      value: figiCount + leveragedCount + failedChecks,
      format: { kind: 'number' },
      tone: figiCount + leveragedCount + failedChecks > 0 ? 'warning' : 'positive',
      sub: `${count(figiCount)} FIGI reviews · ${count(leveragedCount)} leveraged ETFs to curate · ${count(failedChecks)} failed checks`,
    },
  ];

  return (
    <Stack gap={3}>
      {stale && completeness.data && (
        <Banner asOf={stale} title="Latest session not ingested">
          The exchange closed {weekday(completeness.data.lastClosed)}; the newest stored session is{' '}
          {weekday(stale)}. Check the nightly run below.
        </Banner>
      )}
      <StatStrip
        label="Ingestion summary"
        items={items}
        loading={completeness.isPending || quality.isPending || runs.isPending}
        error={completeness.isError ? 'The completeness summary could not load.' : undefined}
      />
    </Stack>
  );
}
