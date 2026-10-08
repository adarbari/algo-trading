/** Test builders for the edge entity (exported for widget tests): edges as the API answers them. */
import type { EdgesResponse } from './edges';
import type { TrackRecordsResponse } from './track-records';

const row = (over: Record<string, unknown>) => ({
  edgeVariant: 'main',
  variant: 'momentum_12_1',
  role: 'screener',
  horizonSessions: 21,
  sliceKind: 'frozen',
  sliceValue: '2024-01-01',
  sessions: 120,
  picks: 2400,
  hitRate: 0.58,
  baseRate: 0.51,
  lift: 1.14,
  exploratory: false,
  ...over,
});

export const EDGES_FIXTURE = {
  edges: [
    {
      id: 'momentum_12_1',
      name: 'Momentum 12-1',
      status: 'candidate',
      thesis: 'Winners keep winning for months.',
      mechanism: 'Slow reaction to news.',
      persistence: 'Limits to arbitrage.',
      schedule: 'Monthly',
      horizons: [21],
      screeners: ['momentum_12_1'],
      baselines: ['equal_weight'],
      variants: ['main'],
      frozenFrom: '2024-01-01',
      rejectionReason: '',
      evidence: null,
      canonicalRun: {
        runId: 'run-frozen',
        owner: 'site',
        rangeFrom: '2012-01-03',
        rangeTo: '2026-10-02',
        splitFrom: '2024-01-01',
        exploratory: false,
        knowledgeTs: '2026-10-05T02:00:00+00:00',
        afterSession: false,
        rows: [
          row({}),
          row({ variant: 'equal_weight', role: 'baseline', hitRate: 0.51, lift: 1 }),
          row({ sliceKind: 'year', sliceValue: '2023', hitRate: 0.9 }),
          row({ exploratory: true, hitRate: 0.99 }),
        ],
      },
      canonicalNotRun: null,
      runs: [
        {
          runId: 'run-frozen',
          owner: 'site',
          rangeFrom: '2012-01-03',
          rangeTo: '2026-10-02',
          splitFrom: '2024-01-01',
          exploratory: false,
          knowledgeTs: '2026-10-05T02:00:00+00:00',
        },
        {
          runId: 'run-explore',
          owner: 'abhinav',
          rangeFrom: '2012-01-03',
          rangeTo: '2026-10-02',
          splitFrom: '2022-06-01',
          exploratory: true,
          knowledgeTs: '2026-10-06T02:00:00+00:00',
        },
      ],
    },
    {
      id: 'sp500_index_changes',
      name: 'S&P 500 index changes',
      status: 'rejected',
      thesis: 'Added names pop.',
      mechanism: 'Index demand.',
      persistence: 'Arbitraged away.',
      schedule: 'Event',
      horizons: [5],
      screeners: [],
      baselines: [],
      variants: ['main'],
      frozenFrom: null,
      rejectionReason: 'The effect vanished after 2005.',
      evidence: null,
      canonicalRun: null,
      canonicalNotRun: {
        code: 'NOT_RUN',
        reason: null,
        kind: 'NOT_RUN',
        guideTerm: 'not_run',
        kindText: 'not run yet',
        cause: null,
      },
      runs: [],
    },
  ],
} as unknown as EdgesResponse;

const horizon = (sessions: number) => ({
  horizonSessions: 21,
  hitRate: 0.58,
  baseRate: 0.51,
  lift: 1.14,
  sessions,
  picks: 2400,
});

export const TRACK_RECORDS_FIXTURE = {
  edges: [
    { id: 'momentum_12_1', status: 'candidate' },
    { id: 'earnings_drift', status: 'evidenced' },
  ],
  screeners: [
    {
      id: 'momentum_12_1',
      trackRecords: [
        {
          screenerId: 'momentum_12_1',
          edgeId: 'momentum_12_1',
          edgeName: 'Momentum 12-1',
          runLabel: 'momentum_12_1 from 2024-01-01 to 2026-10-02',
          afterSession: false,
          notRun: null,
          horizons: [horizon(120)],
        },
        {
          screenerId: 'momentum_12_1',
          edgeId: 'earnings_drift',
          edgeName: 'Earnings drift',
          runLabel: 'earnings_drift from 2024-01-01 to 2026-10-02',
          afterSession: false,
          notRun: null,
          horizons: [horizon(80)],
        },
      ],
    },
    {
      id: 'vrp_scanner',
      trackRecords: [
        {
          screenerId: 'vrp_scanner',
          edgeId: 'vrp',
          edgeName: 'VRP',
          runLabel: null,
          afterSession: false,
          notRun: {
            code: 'NOT_RUN',
            reason: null,
            kind: 'NOT_RUN',
            guideTerm: 'not_run',
            kindText: 'not run yet',
            cause: null,
          },
          horizons: [],
        },
      ],
    },
    { id: 'plain', trackRecords: [] },
  ],
} as unknown as TrackRecordsResponse;
