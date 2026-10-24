/**
 * Entity: edges (ADR 0053), documents whose screeners are tested out of sample: the edges
 * pages' read (`Query.edges`: status, verdict, how it is defined, sources and the runs the user
 * sees) and each screener's track records (`Screener.trackRecords`) for the Screeners
 * list's chip and the Ideas odds line, and the paper record (`Query.edgeDesk`, `Query.edgePaper`:
 * the Ideas signals and an edge's live record) and the sections of an edge's result
 * (`Query.edgeResult`: the evidence curve, drawdown, rolling starts, monthly map, decay, costs,
 * capacity, regimes and horizons, one read each). Never reads an exploratory run as a track record.
 */
export {
  prefetchEdge,
  prefetchEdges,
  refreshEdges,
  useEdge,
  useEdgeDocument,
  useEdgeProblems,
  useEdges,
} from './api/edges';
export { useEdgeTrades, type TradesRequest } from './api/evidence';
export {
  useEdgeCapacity,
  useEdgeCosts,
  useEdgeCurve,
  useEdgeDecay,
  useEdgeDrawdown,
  useEdgeHorizons,
  useEdgeMonthly,
  useEdgeRegimes,
  useEdgeResultBasis,
  useEdgeRollingStarts,
  useEdgeVariants,
} from './api/edge-result';
export { prefetchEdgeDesk, useEdgeDesk, useEdgeLiveStates, useEdgePaper } from './api/paper';
export { useScreenerEdges } from './api/screener-edges';
export { prefetchTrackRecords, useTrackRecords } from './api/track-records';
export {
  EDGE_VIEWS,
  inView,
  labelText,
  sideLabel,
  stateLabel,
  stateOrStatus,
  provenanceLabel,
  provenanceTerm,
  provenanceTone,
  stateTone,
  statusLabel,
  statusTone,
  verdictLabel,
  verdictTone,
  VERDICT_ORDER,
  type Edge,
  type EdgeRow,
  type EdgeDocument,
  type EdgeProblem,
  type EdgeView,
  type EdgesResponse,
  type EdgeVerdict,
  type VerdictCriterion,
  type VerdictYear,
  type VerdictColumn,
  type EvidenceProgress,
} from './model/edges';
export {
  barStateLabel,
  EDGE_UNKNOWN_WORDS,
  excludedLabel,
  measureLabel,
  oosByLabel,
  periodLabel,
  projectionLabel,
  regimeLabel,
  sliceStateLabel,
  tradeStatusLabel,
  tradeStatusTone,
  type DecayBar,
  type DrawdownEpisode,
} from './model/edge-result';
export type {
  EdgeTradePage,
  EdgeTradeRow,
  EdgeVariant,
  EdgeVariants,
  EvidenceUnknown,
  TradeNumber,
  TradePeriod,
  TradeSort,
  VariantFigures,
} from './model/evidence';
export type {
  CurveGap,
  CurvePoint,
  EdgeCapacity,
  EdgeCosts,
  EdgeCurve,
  EdgeDrawdown,
  EdgeHorizons,
  EdgeLive,
  EdgeMonthly,
  EdgeRegimes,
  EdgeResultBasis,
  EdgeResultDecay,
  EdgeRollingStarts,
  HorizonRow,
  RegimeRow,
  SliceFigure,
} from './model/edge-result';
export {
  hasLiveRecord,
  rangeBins,
  rangeMarkers,
  recordLabel,
  recordTone,
  tradeLabel,
  tradeTone,
  tonightLabel,
  tonightTone,
  type DeskTrade,
  type EdgePaper,
  type FollowedEdge,
  type ForwardTest,
  type LiveState,
  type PaperRecord,
  type PaperTrade,
} from './model/paper';
export { screenerEdges, type ScreenerEdge } from './model/screener-edges';
export {
  MIN_TRADES,
  oddsEntry,
  rankedRecords,
  recordFigures,
  screenerEvidence,
  toTrackRecords,
  type EdgeRecord,
  type RecordFigures,
  type ScreenerEvidence,
  type TrackEntry,
} from './model/track-records';
export { EdgeLiveBadge } from './ui/EdgeLiveBadge';
export {
  EDGES_SHOWN,
  ScreenerEvidenceCell,
  ScreenerEvidenceDetail,
  type ScreenerEvidenceCellProps,
  type ScreenerEvidenceDetailProps,
} from './ui/ScreenerEvidence';
export { ScreenerRecord, type ScreenerRecordProps } from './ui/ScreenerRecord';
export {
  CURVE_FIXTURE,
  DECAY_FIXTURE,
  DRAWDOWN_FIXTURE,
  edgeFixture,
  EDGE_ROWS_FIXTURE,
  EDGES_FIXTURE,
  TRACK_RECORDS_FIXTURE,
  UNKNOWN_FIXTURE,
} from './model/fixtures';
export {
  CAPACITY_FIXTURE,
  COSTS_FIXTURE,
  HORIZONS_FIXTURE,
  MONTHLY_FIXTURE,
  REGIMES_FIXTURE,
  ROLLING_STARTS_FIXTURE,
  TRADES_FIXTURE,
  VARIANTS_FIXTURE,
} from './model/fixtures-slices';
