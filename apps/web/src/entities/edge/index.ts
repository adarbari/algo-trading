/**
 * Entity: edges (ADR 0053), documents whose screeners are tested out of sample: the edges
 * pages' read (`Query.edges`: status, verdict, how it is defined, sources and the runs the user
 * sees) and each screener's track records (`Screener.trackRecords`) for the Screeners
 * list's chip and the Ideas odds line, and the paper record (`Query.edgeDesk`, `Query.edgePaper`:
 * the Ideas signals and an edge's live record) and the sections of an edge's result
 * (`Query.edgeResult`: the evidence curve, drawdown, rolling starts, monthly map and decay, one
 * read each). Never reads an exploratory run as a track record.
 */
export { prefetchEdges, refreshEdges, useEdgeProblems, useEdges } from './api/edges';
export {
  useEdgeCurve,
  useEdgeDecay,
  useEdgeDrawdown,
  useEdgeMonthly,
  useEdgeResultBasis,
  useEdgeRollingStarts,
} from './api/edge-result';
export { useEdgeDesk, useEdgeLiveStates, useEdgePaper } from './api/paper';
export { useTrackRecords } from './api/track-records';
export {
  EDGE_VIEWS,
  inView,
  labelText,
  stateLabel,
  stateOrStatus,
  stateTone,
  statusLabel,
  statusTone,
  verdictLabel,
  verdictTone,
  VERDICT_ORDER,
  type Edge,
  type EdgeProblem,
  type EdgeView,
  type EdgesResponse,
  type EdgeVerdict,
  type VerdictCriterion,
  type VerdictYear,
  type VerdictColumn,
  type EvidenceProgress,
} from './model/edges';
export type {
  CurveGap,
  CurvePoint,
  EdgeCurve,
  EdgeDrawdown,
  EdgeLive,
  EdgeMonthly,
  EdgeResultBasis,
  EdgeResultDecay,
  EdgeRollingStarts,
} from './model/edge-result';
export {
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
export {
  oddsEntry,
  recordFigures,
  toTrackRecords,
  type RecordFigures,
  type TrackEntry,
} from './model/track-records';
export { EdgeLiveBadge } from './ui/EdgeLiveBadge';
export { ScreenerEdgeName, ScreenerRecord, type ScreenerRecordProps } from './ui/ScreenerRecord';
export { EDGES_FIXTURE, TRACK_RECORDS_FIXTURE } from './model/fixtures';
