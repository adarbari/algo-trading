/** Test builders for the screener-run entity (exported for widget tests): runs as the API answers them. */
import type { ScreenerRunRecord, ScreenerRunSummary } from './types';

export const summary = (over: Partial<ScreenerRunSummary> = {}): ScreenerRunSummary => ({
  runId: 'screen-trend-site-1',
  configId: 'trend_pullback',
  owner: 'site',
  session: '2026-10-22',
  status: 'complete',
  startedAt: '2026-10-22T22:05:00+00:00',
  finishedAt: '2026-10-22T22:07:00+00:00',
  knowledgeTs: '2026-10-22T22:07:00+00:00',
  picked: 12,
  paused: 3,
  regime: 'Risk on',
  coverage: '480 of 500 screened',
  ...over,
});

export const SUMMARIES_FIXTURE: ScreenerRunSummary[] = [
  summary(),
  summary({
    runId: 'screen-value-abhi-2',
    configId: 'value_dip',
    owner: 'abhi',
    status: 'failed',
    startedAt: '2026-10-21T22:05:00+00:00',
    finishedAt: null,
    knowledgeTs: '2026-10-21T22:05:00+00:00',
    session: '2026-10-21',
    picked: null,
    paused: null,
    regime: null,
    coverage: null,
  }),
];

export const record = (over: Partial<ScreenerRunRecord> = {}): ScreenerRunRecord => ({
  ...summary(),
  configVersion: 3,
  configHash: 'a1b2c3d4',
  decisions: [
    { decision: 'qualified', count: 12 },
    { decision: 'watch', count: 5 },
  ],
  missingTables: [],
  missingOptionalTables: ['rollups/instrument/ibkr_iv@v1'],
  unavailable: [],
  changes: {
    picked: 12,
    paused: 3,
    previousRunId: 'screen-trend-site-0',
    previousSession: '2026-10-21',
    previousVersion: 3,
    newPicks: 4,
    dropped: 2,
  },
  ...over,
});
