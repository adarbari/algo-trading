/** Test builders for the harness-run entity (exported for widget tests): runs as the API answers them. */
import type { HarnessLostInput, HarnessRow, HarnessRun } from './types';

export const run = (over: Partial<HarnessRun> = {}): HarnessRun => ({
  runId: 'run-b',
  edgeId: 'momentum_12_1',
  user: 'site',
  status: 'complete',
  startedAt: '2026-10-05T02:00:00+00:00',
  finishedAt: '2026-10-05T02:10:00+00:00',
  rangeFrom: '2012-01-03',
  rangeTo: '2026-10-02',
  splitFrom: '2024-01-01',
  exploratory: false,
  variants: ['equal_weight', 'momentum_12_1'],
  horizons: [21],
  sessions: 120,
  unclosed: 3,
  excludedCoverage: 2,
  scoreCoverage: 0.92,
  noEntryBar: 7,
  trials: 4,
  knowledgeTs: '2026-10-05T02:10:00+00:00',
  asOf: '2026-10-04T00:00:00+00:00',
  ...over,
});

export const RUNS_FIXTURE: HarnessRun[] = [
  run(),
  run({
    runId: 'run-a',
    user: 'abhi',
    splitFrom: '2022-06-01',
    exploratory: true,
    status: 'failed',
    finishedAt: null,
    startedAt: '2026-10-04T02:00:00+00:00',
    knowledgeTs: '2026-10-04T02:00:00+00:00',
    sessions: null,
    unclosed: null,
    excludedCoverage: null,
    scoreCoverage: null,
    noEntryBar: null,
    trials: null,
    variants: [],
    horizons: [],
  }),
];

export const row = (over: Partial<HarnessRow> = {}): HarnessRow => ({
  edgeVariant: 'main',
  variant: 'momentum_12_1',
  role: 'screener',
  horizonSessions: 21,
  sliceKind: 'frozen',
  sliceValue: '2024-01-01',
  sessions: 120,
  picks: 2400,
  hits: 1392,
  trials: 4,
  hitRate: 0.58,
  baseRate: 0.51,
  lift: 1.14,
  decileSpread: 0.012,
  exploratory: false,
  ...over,
});

export const lostInput = (over: Partial<HarnessLostInput> = {}): HarnessLostInput => ({
  variant: 'main/momentum_12_1',
  horizon: 21,
  table: 'rollups/instrument/ibkr_iv@v1',
  sessions: 4,
  ...over,
});
