/**
 * Entity: edges (ADR 0053), documents whose screeners are tested out of sample: the edges
 * pages' read (`Query.edges`: status, verdict, how it is defined, sources and the runs the user
 * sees) and each screener's track records (`Screener.trackRecords`) for the Screeners
 * list's chip and the Ideas odds line. Never reads an exploratory run as a track record.
 */
export { refreshEdges, useEdges } from './api/edges';
export { refreshEvaluationSplit, useEvaluationSplit } from './api/split';
export { useTrackRecords } from './api/track-records';
export {
  statusLabel,
  statusTone,
  verdictLabel,
  verdictTone,
  VERDICT_ORDER,
  type Edge,
  type EdgesResponse,
  type EdgeVerdict,
  type VerdictCriterion,
  type VerdictYear,
} from './model/edges';
export { chipOf, oddsEntry, toTrackRecords, type TrackEntry } from './model/track-records';
export { ScreenerOdds, type ScreenerOddsProps } from './ui/ScreenerOdds';
export { ScreenerTrackChip } from './ui/ScreenerTrackChip';
export { StoredOdds, type StoredOddsProps } from './ui/StoredOdds';
export { EDGES_FIXTURE, TRACK_RECORDS_FIXTURE } from './model/fixtures';
