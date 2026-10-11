/** Test builders for the edge entity (exported for widget tests): edges as the API answers them. */
import type { Edge, EdgesResponse } from './edges';
import type { TrackRecordsResponse } from './track-records';

const criterion = (id: string, label: string, status: string, level = 'promising') => ({
  id,
  label,
  value: '2.50',
  threshold: 'at least 2',
  status,
  level,
});

const side = (
  period: string,
  winRate: number,
  baseRate: number,
  liftPts: number,
  trades: number,
  thin: boolean,
) => ({
  period,
  winRate,
  baseRate,
  liftPts,
  trades,
  decileSpread: 0.066,
  decileT: 2.4,
  sharpe: 1.0,
  deflatedSharpe: 0.8,
  pbo: null,
  thin,
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
  trials: null,
  deciles: [],
  robustness: null,
  criteria: [],
  years: [],
  columns: [],
  evidence: null,
  haircut: null,
  decay: null,
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
        trials: 3,
        deciles: [0.09, 0.06, 0.04, 0.02, 0.01, -0.005, -0.02, -0.03, -0.05, -0.07],
        robustness: {
          lift: 1.09,
          draws: 1000,
          beats: 0.96,
          summary: 'Beats 96% of 1,000 random backtests after 3 variants tried.',
          bins: [
            { start: 0.8, end: 0.9, count: 120 },
            { start: 0.9, end: 1.0, count: 480 },
            { start: 1.0, end: 1.1, count: 360 },
            { start: 1.1, end: 1.2, count: 40 },
          ],
        },
        columns: [
          side('in_sample', 0.56, 0.5, 6, 64, false),
          side('out_of_sample', 0.57, 0.52, 5, 6, true),
          side('all', 0.56, 0.5, 6, 70, false),
        ],
        evidence: {
          oosTrades: 6,
          needed: 40,
          worksOosNeeded: 60,
          wholeTrades: 70,
          wholeNeeded: 100,
          reached: false,
          checks: [
            criterion('dsr', 'Deflated Sharpe', 'pass'),
            criterion('pbo', 'Chance of overfitting', 'not_measured', 'works'),
          ],
          outlook: {
            criterion: 'trades',
            level: 'promising',
            sentence: 'Promising needs 40 out-of-sample trades: 6 so far, 34 to go.',
            have: 6,
            needed: 40,
            remaining: 34,
            projectionState: 'projected',
            expectedBy: '2027-03-15',
            fillRatio: 0.5,
          },
        },
        haircut: {
          sharpe: 1.1,
          haircutSharpe: 0.4,
          cut: 0.64,
          trials: 3,
          sessions: 70,
          method: 'bonferroni',
          summary: 'Sharpe 1.10 over 70 trades with 3 variants becomes 0.40.',
        },
        criteria: [
          criterion('trades', 'Trades', 'pass'),
          criterion('decile_t', 'Top vs bottom decile t', 'pass'),
          criterion('random', 'Beats random picks', 'not_measured', 'works'),
          criterion('works_t', 'Top vs bottom decile t', 'fail', 'works'),
        ],
        years: [
          {
            year: '2025',
            period: 'in_sample',
            label: '2025',
            fromDate: '2025-01-01',
            toDate: '2025-12-31',
            partial: false,
            winRate: 0.6,
            baseRate: 0.5,
            liftPts: 10,
            decileSpread: 0.128,
            trades: 9,
          },
          {
            year: '2026',
            period: 'in_sample',
            label: '2026 Jan–Mar',
            fromDate: '2026-01-01',
            toDate: '2026-03-31',
            partial: true,
            winRate: 0.5,
            baseRate: 0.5,
            liftPts: 0,
            decileSpread: 0.04,
            trades: 3,
          },
          {
            year: '2026',
            period: 'out_of_sample',
            label: '2026 Apr–Dec',
            fromDate: '2026-04-01',
            toDate: '2026-12-31',
            partial: true,
            winRate: 0.6,
            baseRate: 0.53,
            liftPts: 7,
            decileSpread: 0.08,
            trades: 3,
          },
        ],
      }),
      canonicalRun: { runId: 'run-frozen', knowledgeTs: '2026-10-05T02:00:00+00:00' },
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

const unknown = (kind: string, kindText: string, guideTerm: string) => ({
  code: 'UNKNOWN',
  reason: null,
  kind,
  guideTerm,
  kindText,
  cause: null,
});

/** The evidence curve of momentum_12_1 as `edgeResult.curve` answers it (test builder). */
export const CURVE_FIXTURE = {
  kind: 'cumulative_excess',
  unit: 'return',
  splitFrom: '2026-04-01',
  hidden: false,
  points: [
    {
      decision: '2026-01-02',
      exit: '2026-02-02',
      period: 'in_sample',
      value: 0.01,
      cumulative: 0.01,
      baseValue: 0.002,
      baseCumulative: 0.002,
      trades: 1,
    },
    {
      decision: '2026-03-02',
      exit: '2026-04-02',
      period: 'in_sample',
      value: 0.02,
      cumulative: 0.03,
      baseValue: 0.002,
      baseCumulative: 0.004,
      trades: 1,
    },
    {
      decision: '2026-05-04',
      exit: '2026-06-03',
      period: 'out_of_sample',
      value: -0.01,
      cumulative: 0.02,
      baseValue: 0.002,
      baseCumulative: 0.006,
      trades: 1,
    },
  ],
  gaps: [{ from: '2026-02-10', to: '2026-02-20', kind: 'lost_input', unknown: null }],
  live: {
    state: 'recorded',
    since: '2026-08-03',
    anchor: 0.02,
    closed: 2,
    sessions: 2,
    points: [
      { sell: '2026-09-03', value: 0.004, cumulative: 0.024, trades: 1 },
      { sell: '2026-10-02', value: -0.002, cumulative: 0.022, trades: 1 },
    ],
  },
  unknown: null,
};

/** The drawdown of momentum_12_1 as `edgeResult.drawdown` answers it (test builder). */
export const DRAWDOWN_FIXTURE = {
  unit: 'return',
  points: [
    { exit: '2026-02-02', depth: 0 },
    { exit: '2026-04-02', depth: 0 },
    { exit: '2026-06-03', depth: -0.01 },
  ],
  episodes: [
    { peak: '2026-04-02', trough: '2026-06-03', recovered: null, depth: 0.01 },
    { peak: '2026-01-02', trough: '2026-01-20', recovered: '2026-02-02', depth: 0.005 },
  ],
  maxInSample: 0.005,
  maxOutOfSample: 0.01,
  volInSample: 0.12,
  volOutOfSample: null,
  unknown: null,
};

/** The decay of momentum_12_1 as `edgeResult.decay` answers it: the paper's bar not given (test builder). */
export const DECAY_FIXTURE = {
  measure: 'lift_pts',
  unit: 'points',
  basisHorizon: 20,
  published: null,
  bars: [
    { period: 'published', value: null, n: null, state: 'not_given' },
    { period: 'in_sample', value: 6, n: 64, state: 'measured' },
    { period: 'out_of_sample', value: 5, n: 6, state: 'measured' },
    { period: 'live', value: null, n: 0, state: 'not_measured_live' },
  ],
};

/** A gap in a section's read the server explains (test builder): why a curve or drawdown is not there. */
export const UNKNOWN_FIXTURE = unknown(
  'NOT_STORED',
  'not stored for this run',
  'unavailable_not_stored',
);

/** One edge of {@link EDGES_FIXTURE} by id (test builder): fails loudly when the id is not there. */
export function edgeFixture(id: string): Edge {
  const found = EDGES_FIXTURE.edges.find((e) => e.id === id);
  if (!found) throw new Error(`no edge ${id} in the fixture`);
  return found;
}
