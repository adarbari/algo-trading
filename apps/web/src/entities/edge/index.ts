/**
 * Entity: edges (ADR 0053), documents whose screeners are tested out of sample: the edges
 * pages' read (`Query.edges`: status, verdict, how it is defined, sources and the runs the user
 * sees) and each screener's track records (`Screener.trackRecords`) for the Screeners
 * list's chip and the Ideas odds line. Never reads an exploratory run as a track record.
 */
export { prefetchEdges, refreshEdges, useEdgeProblems, useEdges } from './api/edges';
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
} from './model/edges';
export {
  oddsEntry,
  recordFigures,
  toTrackRecords,
  type RecordFigures,
  type TrackEntry,
} from './model/track-records';
export { ScreenerEdgeName, ScreenerRecord, type ScreenerRecordProps } from './ui/ScreenerRecord';
export { EDGES_FIXTURE, TRACK_RECORDS_FIXTURE } from './model/fixtures';
