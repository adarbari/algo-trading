/** Test builders for the lower sections of an edge's page, as the API answers them (exported for widget tests). */

const figure = (
  period: string,
  winRate: number | null,
  baseRate: number | null,
  liftPts: number | null,
  trades: number | null,
  thin = false,
  state = 'measured',
) => ({ period, state, winRate, baseRate, liftPts, trades, thin });

/** `edgeResult.regimes`: calm has no trades, crisis rests on one. */
export const REGIMES_FIXTURE = {
  state: 'measured',
  variant: 'main',
  horizon: 20,
  rows: [
    {
      regime: 'CALM',
      figures: [
        figure('in_sample', null, null, null, 0),
        figure('out_of_sample', null, null, null, 0),
        figure('all', null, null, null, 0),
      ],
    },
    {
      regime: 'CAUTION',
      figures: [
        figure('in_sample', 0.7, 0.66, 4, 11),
        figure('out_of_sample', 0.72, 0.696, 2.5, 14),
        figure('all', 0.71, 0.68, 3, 25),
      ],
    },
    {
      regime: 'CRISIS',
      figures: [
        figure('in_sample', null, null, null, null, false, 'not_stored'),
        figure('out_of_sample', 0.75, 0.885, -13.5, 1, true),
        figure('all', 0.75, 0.885, -13.5, 1, true),
      ],
    },
  ],
};

const oosBy = (state: string, needed: number, have: number | null, expectedBy: string | null) => ({
  state,
  needed,
  have,
  remaining: have == null ? null : needed - have,
  expectedBy,
  fillRatio: null,
});

/** `edgeResult.horizons`: the 20-session row is the verdict's basis. */
export const HORIZONS_FIXTURE = {
  state: 'measured',
  variant: 'main',
  needed: 40,
  rows: [
    {
      horizon: 10,
      basis: false,
      figures: [
        figure('in_sample', 0.6, 0.61, -1.5, 25),
        figure('out_of_sample', 0.7, 0.65, 4.7, 8),
        figure('all', 0.62, 0.62, 0, 33),
      ],
      oosBy: oosBy('projected', 40, 8, '2028-08-01'),
    },
    {
      horizon: 20,
      basis: true,
      figures: [
        figure('in_sample', 0.6, 0.601, -0.1, 12),
        figure('out_of_sample', 0.8, 0.724, 7.6, 3, true),
        figure('all', 0.63, 0.615, 1.5, 15),
      ],
      oosBy: oosBy('beyond_projection', 40, 3, null),
    },
  ],
};

const level = (period: string, bp: number, assumed: boolean, liftPts: number | null) => ({
  period,
  bp,
  assumed,
  sessions: 30,
  picks: 30,
  winRate: 0.7,
  baseRate: 0.65,
  liftPts,
  meanExcess: 0.01,
});

/** `edgeResult.costs`: four levels, the document's own cost at 15 bp. */
export const COSTS_FIXTURE = {
  state: 'measured',
  variant: 'main',
  horizon: 20,
  assumedBp: 15,
  levels: [
    level('out_of_sample', 0, false, 1.9),
    level('out_of_sample', 15, true, -0.3),
    level('out_of_sample', 30, false, -2.1),
    level('in_sample', 0, false, 0.4),
  ],
  periods: [
    { period: 'in_sample', state: 'measured', breakEvenBp: 4, decileSpread: 0.04 },
    { period: 'out_of_sample', state: 'measured', breakEvenBp: 13, decileSpread: 0.066 },
    { period: 'all', state: 'not_stored', breakEvenBp: null, decileSpread: null },
  ],
};

/** `edgeResult.capacity`: the site floor and the median volume of the picks. */
export const CAPACITY_FIXTURE = {
  state: 'measured',
  variant: 'main',
  horizon: 20,
  floorUsd: 5_000_000,
  periods: [
    {
      period: 'in_sample',
      state: 'measured',
      picks: 40,
      advMedian: 4.1e8,
      advKnown: 38,
      advLow: 6,
    },
    {
      period: 'out_of_sample',
      state: 'measured',
      picks: 15,
      advMedian: 3.9e8,
      advKnown: 15,
      advLow: 2,
    },
    {
      period: 'all',
      state: 'oos_hidden',
      picks: null,
      advMedian: null,
      advKnown: null,
      advLow: null,
    },
  ],
};

/** `edgeResult.rollingStarts`. */
export const ROLLING_STARTS_FIXTURE = {
  unit: 'points',
  starts: [
    { start: '2025-01-02', trades: 40, liftPts: 2.1, meanExcess: 0.004 },
    { start: '2025-07-01', trades: 22, liftPts: -0.5, meanExcess: -0.001 },
  ],
  unknown: null,
};

/** `edgeResult.monthly`: two years' months, one of them out-of-sample. */
export const MONTHLY_FIXTURE = {
  unit: 'return',
  months: [
    { month: '2025-11', value: 0.01, trades: 3, period: 'in_sample' },
    { month: '2025-12', value: -0.02, trades: 2, period: 'in_sample' },
    { month: '2026-01', value: 0.004, trades: 2, period: 'out_of_sample' },
  ],
  unknown: null,
};

const evidenceUnknown = (kind: string, code: string) => ({
  code,
  kind,
  guideTerm: 'trade_ledger_unavailable',
  kindText: 'Not available',
});

const cell = (value: number | null) => ({ value, unknown: null });

const trade = (over: Record<string, unknown>) => ({
  variant: 'main',
  horizonSessions: 20,
  decisionSession: '2026-04-06',
  entrySession: '2026-04-07',
  exitSession: '2026-05-05',
  instrumentId: 'US-AAA',
  rank: 3,
  status: 'won',
  excludedReason: null,
  hit: true,
  delisted: false,
  beforeSplit: false,
  source: 'backtest',
  score: cell(1.2),
  value: cell(0.031),
  grossValue: cell(0.034),
  maxDrawdown: -0.02,
  advUsd: cell(4.2e8),
  reference: cell(0.01),
  touch: { value: false, unknown: null },
  ...over,
});

/** `edgeTrades`: a page of three trades, one with its licensed score hidden, one open and one excluded. */
export const TRADES_FIXTURE = {
  period: 'ALL',
  page: 1,
  pageSize: 2,
  total: 3,
  basis: 'main at 20 sessions',
  licence: null,
  oosHidden: false,
  unknown: null,
  rows: [
    trade({}),
    trade({
      instrumentId: 'US-BBB',
      status: 'excluded',
      excludedReason: 'NO_ENTRY_BAR',
      hit: null,
      beforeSplit: true,
      score: { value: null, unknown: evidenceUnknown('LICENCE', 'LICENCE') },
      value: { value: null, unknown: evidenceUnknown('NOT_STORED', 'NOT_STORED') },
    }),
  ],
};

const variantFigures = (liftPts: number, trades: number) => ({
  winRate: 0.7,
  baseRate: 0.65,
  liftPts,
  decileSpread: 0.05,
  trades,
});

/** `edgeVariants`: the official variant at two horizons plus one other screen not pre-chosen. */
export const VARIANTS_FIXTURE = {
  basis: 'main at 20 sessions',
  trials: 6,
  oosHidden: false,
  unknown: null,
  rows: [
    {
      edgeVariant: 'main',
      variant: 'main',
      horizonSessions: 20,
      inSample: variantFigures(-0.1, 12),
      outOfSample: variantFigures(7.6, 3),
      all: variantFigures(1.5, 15),
      official: true,
      notPreChosen: false,
      modelFit: false,
    },
    {
      edgeVariant: 'main',
      variant: 'main',
      horizonSessions: 10,
      inSample: variantFigures(-1.5, 25),
      outOfSample: variantFigures(4.7, 8),
      all: null,
      official: false,
      notPreChosen: true,
      modelFit: false,
    },
  ],
};
