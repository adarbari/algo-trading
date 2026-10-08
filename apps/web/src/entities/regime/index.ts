/**
 * Entity: the market regime for the session (ADR 0047): `Query.regime` read as one `Regime`
 * (label as weather, headline, scores, indicator cards, sizing), the label history of a window
 * as bands, the reference episodes and NBER recessions the session knows, the chip and
 * headline views, the mapping of bands to chart props, and the history of stored market fields
with the chart props the regime pages build from it (lines, lanes, bands, threshold lines).
 */
export {
  MARKET_HISTORY_OPERATION,
  REGIME_BANDS_OPERATION,
  REGIME_EPISODES_OPERATION,
  REGIME_OPERATION,
  useMarketHistory,
  useRegime,
  useRegimeBands,
  useRegimeEpisodes,
} from './api/hooks';
export { regimeFixture, unknownRegimeFixture } from './model/fixtures';
export {
  BAND_LABELS,
  episodeBands,
  evidenceLane,
  FULL_EVIDENCE,
  LANE_LABELS,
  regimeLane,
  signalLane,
  toChartPoints,
  toHistoryChart,
  type HistoryChartProps,
  type HistoryPoint,
  type HistorySegment,
  type HistoryWindow,
  type SeriesHistory,
  type SeriesInput,
} from './model/history';
export {
  indicatorFormat,
  meterDirection,
  meterThresholds,
  NOT_USED_TODAY,
  onWhenLine,
  provenanceLine,
  sourceItems,
} from './model/indicator';
export {
  episodeWindow,
  HISTORY_START,
  presetWindow,
  RANGE_PRESETS,
  type RangePreset,
} from './model/window';
export {
  changedIndicators,
  episodeName,
  gateLine,
  gatePauses,
  indicatorChange,
  indicatorsOfPace,
  indicatorStatus,
  plainLabel,
  regimeLabelFeature,
  regimeTone,
  sizingLine,
  storedLabel,
  toChartBands,
  type Recession,
  type Regime,
  type RegimeBand,
  type RegimeEpisode,
  type RegimeIndicator,
  type RegimeLabel,
  type RegimeScore,
  type RegimeSizing,
  type ScreenerGate,
  type RegimeUnknown,
  type IndicatorSource,
  type TextPart,
} from './model/regime';
export { RegimeChip, type RegimeChipProps } from './ui/RegimeChip';
export { RegimeHeadline, type RegimeHeadlineProps } from './ui/RegimeHeadline';
export { RunRegimeChip, type RunRegimeChipProps } from './ui/RunRegimeChip';
