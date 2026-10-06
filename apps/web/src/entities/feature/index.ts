/**
 * Entity: the feature catalogue (definitions, units, formats, the site field guide's entry per
 * field: how to read it, the criterion per intent, caveats), feature distributions, how a
 * served feature value reads (format from the server, UNKNOWN reasons), the feature table
 * (instruments x catalogue columns, one page per request) and the column factories every
 * table is built from (ADR 0038).
 */
export { refreshCatalogue, useFeatureCatalogue, useFeatureDistribution } from './api/hooks';
export { useFeatureTable } from './api/table';
export {
  catalogueColumn,
  changeColumn,
  criterionColumn,
  decisionColumn,
  featureColumn,
  flagsColumn,
  fromHighColumn,
  rankColumn,
  reasonsColumn,
  scoreColumn,
  screenColumn,
  TICKER_COLUMN,
  tickerColumn,
  withCompanions,
  type ColumnPlan,
  type CriterionInfo,
  type ScreenColumnInfo,
} from './model/columns';
export {
  tableVariables,
  toTableData,
  type ColumnInfo,
  type FeatureTableData,
  type FeatureTableQuery,
  type TableCell,
  type TableFilters,
  type TableRow,
} from './model/table';
export {
  byName,
  displayValue,
  columnOf,
  featureFormat,
  featureGroup,
  featureLabel,
  featureMarks,
  featureTitle,
  isNumericFeature,
  isOwn,
  isPersonal,
  unitLabel,
  type CatalogueFeature,
} from './model/catalogue';
export { guideTolerance, guideValues, type FieldGuide, type GuideUse } from './model/guide';
export {
  codeReason,
  isUnknown,
  reasonLabel,
  shownValue,
  unknownLabel,
  unknownReason,
  valueFormat,
  type FeatureFormatName,
  type NullReasonName,
  type ServedInfo,
  type ServedValue,
  type UnknownCodeName,
} from './model/value';
export {
  distributionBins,
  distributionCategories,
  distributionMarkers,
  type FeatureDistribution,
} from './model/distribution';
