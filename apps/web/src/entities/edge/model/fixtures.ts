/** Test builders for the edge entity (exported for widget tests): edges as the API answers them. */
import type { EdgesResponse } from './edges';
import type { TrackRecordsResponse } from './track-records';

const criterion = (id: string, label: string, status: string, level = 'promising') => ({
  id,
  label,
  value: '2.50',
  threshold: 'at least 2',
  status,
  level,
});

const verdict = (over: Record<string, unknown>) => ({
  verdict: 'waiting_on_data',
  rationale: 'No official result yet',
  headline: 'No official result yet',
  result: 'No official result yet',
  basis: null,
  trades: null,
  oosTrades: null,
  winRate: null,
  baseRate: null,
  liftPts: null,
  lift: null,
  decileSpread: null,
  decileT: null,
  sharpe: null,
  deflatedSharpe: null,
  pbo: null,
  criteria: [],
  years: [],
  ...over,
});

const edge = (over: Record<string, unknown>) => ({
  status: 'candidate',
  state: 'researching',
  since: null,
  stateReason: '',
  labels: [],
  oosRevealed: false,
  oosHidden: false,
  mine: false,
  extends: null,
  replaces: null,
  compare: null,
  thesis: 'Winners keep winning for months.',
  mechanism: 'Slow reaction to news.',
  persistence: 'Limits to arbitrage.',
  horizons: [20],
  screeners: [],
  baselines: [],
  rejectionReason: '',
  sources: [],
  definition: {
    picks: 'Every month end · top 50 of the screen',
    trade:
      'Enter 1 session after the decision · hold 20 trading days · 0.1% costs · win = beats SPY',
    compare: 'Universe: liquid_common_stocks · against equal_weight',
    test: 'Out-of-sample from 2026-04-01',
  },
  verdict: verdict({}),
  canonicalRun: null,
  runs: [],
  ...over,
});

const figures = (winRate: number, baseRate: number, trades: number) => ({
  winRate,
  baseRate,
  liftPts: Math.round((winRate - baseRate) * 100),
  decileSpread: 0.05,
  trades,
});

export const EDGES_FIXTURE = {
  edgeProblems: [{ edgeId: 'broken', reason: "broken.toml extends: no edge 'ghost'" }],
  edges: [
    edge({
      id: 'momentum_12_1',
      name: 'Momentum 12-1',
      screeners: ['momentum_12_1'],
      baselines: ['equal_weight'],
      sources: [
        { title: 'Jegadeesh and Titman 1993', url: 'https://example.org/jt1993' },
        { title: 'Daniel and Moskowitz 2016', url: '' },
      ],
      verdict: verdict({
        verdict: 'promising',
        rationale: 'Trades, and out-of-sample trades is 70 and 6; it needs at least 100 and 40',
        headline:
          'Out-of-sample, momentum_12_1, 20 trading days: win rate 57% against a base rate of 52% (5 pts).',
        result: 'Win rate 57% · base rate 52%',
        basis: 'momentum_12_1, 20 trading days',
        trades: 70,
        oosTrades: 6,
        winRate: 0.57,
        baseRate: 0.52,
        liftPts: 5,
        lift: 1.09,
        decileSpread: 0.067,
        decileT: 2.5,
        sharpe: 1.1,
        deflatedSharpe: 0.9,
        pbo: 0.3,
        criteria: [
          criterion('trades', 'Trades', 'pass'),
          criterion('decile_t', 'Top vs bottom decile t', 'pass'),
          criterion('random', 'Beats the best random-pick backtest', 'not_measured', 'works'),
          criterion('works_t', 'Top vs bottom decile t', 'fail', 'works'),
        ],
        years: [
          {
            year: '2025',
            period: 'in_sample',
            winRate: 0.6,
            baseRate: 0.5,
            liftPts: 10,
            decileSpread: 0.128,
            trades: 9,
          },
          {
            year: '2026',
            period: 'both',
            winRate: 0.57,
            baseRate: 0.52,
            liftPts: 5,
            decileSpread: 0.067,
            trades: 6,
          },
        ],
      }),
      canonicalRun: { runId: 'run-frozen' },
      runs: [
        {
          runId: 'run-frozen',
          owner: 'site',
          rangeFrom: '2012-01-03',
          rangeTo: '2026-10-02',
          splitFrom: '2026-04-01',
          exploratory: false,
          knowledgeTs: '2026-10-05T02:00:00+00:00',
          trialsCounted: 3,
          lostInputs: ['momentum_12_1: rollup (4 sessions)'],
        },
        {
          runId: 'run-explore',
          owner: 'abhinav',
          rangeFrom: '2012-01-03',
          rangeTo: '2026-10-02',
          splitFrom: '2022-06-01',
          exploratory: true,
          knowledgeTs: '2026-10-06T02:00:00+00:00',
          trialsCounted: 4,
          lostInputs: [],
        },
      ],
    }),
    edge({
      id: 'my_momentum',
      name: 'My momentum',
      mine: true,
      extends: 'momentum_12_1',
      oosHidden: true,
      screeners: ['momentum_12_1'],
      compare: {
        oosHidden: true,
        reason: '',
        rows: [
          {
            kind: 'this',
            label: 'My momentum',
            basis: 'momentum_12_1, 20 trading days',
            oosHidden: true,
            inSample: figures(0.6, 0.5, 40),
            outOfSample: null,
          },
          {
            kind: 'extended',
            label: 'Momentum 12-1',
            basis: 'momentum_12_1, 20 trading days',
            oosHidden: false,
            inSample: figures(0.58, 0.5, 70),
            outOfSample: figures(0.57, 0.52, 6),
          },
        ],
      },
    }),
    edge({
      id: 'earnings_drift',
      name: 'Earnings drift',
      status: 'evidenced',
      screeners: ['pead', 'pead_volume'],
      verdict: verdict({
        verdict: 'not_working',
        rationale:
          'Out-of-sample win rate above the base rate is 49% against 51%; it needs above the base rate',
        headline: 'Out-of-sample: win rate 49% against a base rate of 51%.',
        result: 'Win rate 49% · base rate 51%',
        trades: 74,
      }),
    }),
    edge({
      id: 'sp500_index_changes',
      name: 'S&P 500 index changes',
      status: 'rejected',
      rejectionReason: 'The effect vanished after 2005.',
    }),
  ],
} as unknown as EdgesResponse;

const horizon = (sessions: number) => ({
  horizonSessions: 21,
  hitRate: 0.58,
  baseRate: 0.51,
  lift: 1.14,
  liftPts: 7,
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
