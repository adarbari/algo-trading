/**
 * Entity: one instrument's detail pane over GraphQL: its facts for a session (identity and
 * catalogue features), events, daily bars, and feature values and history.
 */
export {
  NAMES_PER_REQUEST,
  useFeatureHistory,
  useFeatureValues,
  useInstrumentEvents,
  useInstrumentPrices,
} from './api/hooks';
export { useInstrumentFacts } from './api/facts';
export {
  chunks,
  historyOf,
  type FeatureHistory,
  type FeatureValues,
  type SeriesChunk,
} from './model/values';
export {
  earningsOn,
  reportTime,
  splitRatio,
  toChartEvents,
  toTimeline,
  type EarningsReport,
  type EventKind,
  type InstrumentEvent,
  type TimelineEvent,
} from './model/events';
export { ALL_HISTORY, rangeFrom } from './model/range';
export { RangeControl, type RangeControlProps } from './ui/RangeControl';
