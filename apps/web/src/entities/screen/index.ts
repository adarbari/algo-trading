/**
 * Entity: rule screens (the draft document, its criteria, the live preview, the list, and a
 * screener's latest run as a review table).
 */
export {
  PREVIEW_ROWS,
  forgetScreen,
  refreshScreens,
  useMyScreeners,
  useRunScreener,
  useScreener,
  useScreenerVersions,
  useScreenPreview,
  useScreeners,
} from './api/hooks';
export { useScreenerRuns, type ScreenerRunSummary } from './api/runs';
export { useScreenerHits, type ScreenerHitsResponse } from './api/hits';
export {
  SCREENER_RESULTS_OPERATION,
  useScreenerResults,
  type ScreenerResultsResponse,
} from './api/results';
export {
  decisionCounts,
  extraColumns,
  narrowMissGroups,
  type FunnelStep,
  type NarrowMiss,
  type PreviewChanges,
  type PreviewRow,
  type PreviewSummary,
  type ScreenPreview,
} from './model/preview';
export {
  blankDocument,
  criteriaOf,
  criterionIds,
  criterionOfError,
  isComplete,
  isScreenId,
  MISS_DECISIONS,
  MODES,
  newCriterionId,
  NO_VALUE_OPS,
  previewDocument,
  tieBreakOf,
  toDocument,
  withCriterion,
  withoutCriterion,
  withTieBreak,
  type Criterion,
  type CriterionMode,
  type MissDecision,
  type PresetPin,
  type ScreenDocument,
  type ScreenerDetail,
  type ScreenerListItem,
  type ScreenerSummary,
  type Tolerance,
} from './model/spec';
export { DecisionBadge } from './ui/DecisionBadge';
export { decisionLabel, decisionTone, OUTCOME_FILL, type DecisionTone } from './model/decisions';
export { ScoreBreakdown } from './ui/ScoreBreakdown';
export { scoreBreakdown, type ScoreLine } from './model/score';
export {
  DEFAULT_DECISIONS,
  isShownCriterion,
  orderedDecisions,
  resultsVariables,
  shownDecisions,
  type ScreenChange,
  type ScreenResultsQuery,
} from './model/results';
export { isActive, runMessage, type ScreenRun } from './model/run';
