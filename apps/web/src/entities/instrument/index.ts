/**
 * Entity: one instrument: its facts for a session (GraphQL: identity and catalogue features),
 * detail, daily bars, events and feature history.
 */
export {
  useFeatureHistory,
  useInstrument,
  useInstrumentBars,
  useInstrumentEvents,
} from './api/hooks';
export { useInstrumentFacts } from './api/facts';
export {
  displayName,
  fieldValue,
  historyOf,
  type FeatureSeries,
  type InstrumentDetail,
} from './model/detail';
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
