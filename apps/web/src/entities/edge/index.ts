/**
 * Entity: edges (ADR 0053), documents whose screeners are tested over a frozen period: the
 * edges page's read (`Query.edges`: status, frozen period, the canonical run's rows and the runs
 * the user sees) and each screener's track records (`Screener.trackRecords`) for the Screeners
 * list's chip and the Ideas odds line. Never reads an exploratory run as a track record.
 */
export { useEdges } from './api/edges';
export { refreshEvaluationSplit, useEvaluationSplit } from './api/split';
export { useTrackRecords } from './api/track-records';
export {
  frozenRows,
  statusLabel,
  statusTone,
  toEdges,
  type Edge,
  type EdgesResponse,
  type FrozenRow,
} from './model/edges';
export { chipOf, oddsEntry, toTrackRecords, type TrackEntry } from './model/track-records';
export { ScreenerTrackChip } from './ui/ScreenerTrackChip';
export { StoredOdds, type StoredOddsProps } from './ui/StoredOdds';
export { EDGES_FIXTURE, TRACK_RECORDS_FIXTURE } from './model/fixtures';
