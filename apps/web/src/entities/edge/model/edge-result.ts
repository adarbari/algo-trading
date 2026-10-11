/**
 * The sections of an edge's result as the pages show them (ADR 0064): the types of the served
 * `edgeResult` sections. Every number, date, sentence and state is the read model's; this only
 * names the shapes.
 */
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
