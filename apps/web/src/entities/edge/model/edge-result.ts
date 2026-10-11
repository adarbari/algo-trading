/**
 * The sections of an edge's result as the pages show them (ADR 0064): the types of the served
 * `edgeResult` sections. Every number, date, sentence and state is the read model's; this only
 * names the shapes.
 */
import type { StatusTone } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

export type EdgeResultBasis = NonNullable<gqlTypes.EdgeResultBasisQuery['edgeResult']>['basis'];
export type EdgeCurve = NonNullable<gqlTypes.EdgeResultCurveQuery['edgeResult']>['curve'];
export type CurvePoint = EdgeCurve['points'][number];
export type CurveGap = EdgeCurve['gaps'][number];
export type EdgeLive = NonNullable<EdgeCurve['live']>;
export type EdgeDrawdown = NonNullable<gqlTypes.EdgeResultDrawdownQuery['edgeResult']>['drawdown'];
export type EdgeRollingStarts = NonNullable<
  gqlTypes.EdgeResultRollingStartsQuery['edgeResult']
>['rollingStarts'];
export type EdgeMonthly = NonNullable<gqlTypes.EdgeResultMonthlyQuery['edgeResult']>['monthly'];
export type EdgeResultDecay = NonNullable<
  NonNullable<gqlTypes.EdgeResultDecayQuery['edgeResult']>['decay']
>;
export type EdgeCosts = NonNullable<gqlTypes.EdgeResultCostsQuery['edgeResult']>['costs'];
export type EdgeCapacity = NonNullable<gqlTypes.EdgeResultCapacityQuery['edgeResult']>['capacity'];
export type EdgeRegimes = NonNullable<gqlTypes.EdgeResultRegimesQuery['edgeResult']>['regimes'];
export type RegimeRow = EdgeRegimes['rows'][number];
export type SliceFigure = RegimeRow['figures'][number];
export type EdgeHorizons = NonNullable<gqlTypes.EdgeResultHorizonsQuery['edgeResult']>['horizons'];
export type HorizonRow = EdgeHorizons['rows'][number];
export type DecayBar = EdgeResultDecay['bars'][number];
export type DrawdownEpisode = EdgeDrawdown['episodes'][number];

const PERIOD_LABELS: Record<string, string> = {
  published: 'Published',
  in_sample: 'In-sample',
  out_of_sample: 'Out-of-sample',
  live: 'Live',
  all: 'All',
};

/** The side of the split a figure, bar or row belongs to, in words. */
export const periodLabel = (period: string): string => PERIOD_LABELS[period] ?? period;

const BAR_STATE_LABELS: Record<string, string> = {
  measured: 'Measured',
  not_stored: 'Not stored',
  not_comparable: 'Not comparable',
  oos_hidden: 'Hidden',
  not_given: 'Not given',
  not_measured_live: 'Not measured live',
};

/** What a decay bar without a value says (the state's words). */
export const barStateLabel = (state: string): string => BAR_STATE_LABELS[state] ?? state;

const PROJECTION_LABELS: Record<string, string> = {
  projected: 'Projected',
  not_stored: 'Not projected: older run',
  beyond_projection: 'Beyond the projection',
  unprojectable: 'Not projected: event schedule',
  oos_hidden: 'Hidden',
};

/** The words for a count's projection state (a date, or why there is none). */
export const projectionLabel = (state: string): string => PROJECTION_LABELS[state] ?? state;

const MEASURE_LABELS: Record<string, string> = {
  mean_excess: 'Mean excess return',
  decile_spread: 'Top vs bottom decile',
  lift_pts: 'Lift',
};

/** The statistic the decay bars compare. */
export const measureLabel = (measure: string): string => MEASURE_LABELS[measure] ?? measure;

/** The words of an unknown on an edge's page, in its own subject (a result, an outcome), not an instrument's. */
export const EDGE_UNKNOWN_WORDS = {
  NOT_STORED: 'Not stored for this result',
  NOT_APPLICABLE: 'Does not apply to this outcome',
} as const;

const SLICE_STATE_LABELS: Record<string, string> = {
  measured: 'Measured',
  not_stored: 'Not stored',
  oos_hidden: 'Hidden',
  not_a_cost_outcome: 'Not a cost outcome',
};

/** What a result section's figure without a value says (the state's words; also cost and capacity states). */
export const sliceStateLabel = (state: string): string => SLICE_STATE_LABELS[state] ?? state;

const OOS_BY_LABELS: Record<string, string> = {
  not_stored: 'Not projected: older run',
  beyond_projection: 'Beyond the projection',
  unprojectable: 'Not projected: event schedule',
  oos_hidden: 'Hidden',
  reached: 'Reached',
};

/** The words for the "needed out-of-sample by" cell of a holding period that has no date. */
export const oosByLabel = (state: string): string => OOS_BY_LABELS[state] ?? state;

const REGIME_LABELS: Record<string, string> = {
  CALM: 'Calm',
  CAUTION: 'Caution',
  STRESS: 'Stress',
  CRISIS: 'Crisis',
};

/** A market regime's label in words. */
export const regimeLabel = (regime: string): string =>
  REGIME_LABELS[regime.toUpperCase()] ?? regime;

const TRADE_STATUS_LABELS: Record<string, string> = {
  won: 'Won',
  lost: 'Lost',
  excluded: 'Excluded',
  open: 'Open',
};

/** A ledger trade's status in words. */
export const tradeStatusLabel = (status: string): string => TRADE_STATUS_LABELS[status] ?? status;

const TRADE_STATUS_TONES: Record<string, StatusTone> = {
  won: 'positive',
  lost: 'negative',
  excluded: 'warning',
  open: 'info',
};

/** The tone of a ledger trade's status badge. */
export const tradeStatusTone = (status: string): StatusTone =>
  TRADE_STATUS_TONES[status] ?? 'neutral';

const EXCLUDED_LABELS: Record<string, string> = {
  UNMEASURED: 'Unmeasured',
  MISSING_VALUE: 'Missing value',
  NO_ENTRY_BAR: 'No entry bar',
  NO_IMPLIED_VOL: 'No implied volatility',
  MISSING_DRAWDOWN: 'Missing drawdown',
  SKIPPED: 'Skipped',
};

/** The public reason a pick is excluded, in words. */
export const excludedLabel = (reason: string): string => EXCLUDED_LABELS[reason] ?? reason;
