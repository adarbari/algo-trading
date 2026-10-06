/**
 * Entity: the market regime for the session (ADR 0047): `Query.regime` read as one `Regime`
 * (label as weather, headline, scores, indicator cards, sizing) and the label history of a
 * window as bands, the chip and headline views, and the mapping of bands to chart props.
 */
export { REGIME_BANDS_OPERATION, REGIME_OPERATION, useRegime, useRegimeBands } from './api/hooks';
export { regimeFixture, unknownRegimeFixture } from './model/fixtures';
export {
  changedIndicators,
  indicatorChange,
  indicatorsOfPace,
  indicatorStatus,
  plainLabel,
  readingList,
  regimeTone,
  sizingLine,
  toChartBands,
  type Regime,
  type RegimeBand,
  type RegimeIndicator,
  type RegimeLabel,
  type RegimeScore,
  type RegimeUnknown,
  type ReadingLink,
} from './model/regime';
export { RegimeChip, type RegimeChipProps } from './ui/RegimeChip';
export { RegimeHeadline, type RegimeHeadlineProps } from './ui/RegimeHeadline';
