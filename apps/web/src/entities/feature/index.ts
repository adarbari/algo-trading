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
  fieldColumn,
  flagsColumn,
  fromHighColumn,
  rankColumn,
  reasonsColumn,
  scoreColumn,
  screenColumn,
  TICKER_COLUMN,
  tickerColumn,
  withCompanions,
  type ColumnHelp,
  type ColumnPlan,
  type HelpedColumn,
  type PlanColumn,
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
export {
  guideTolerance,
  guideValues,
  ruleText,
  bandOf,
  type FieldGuide,
  type GuideUse,
} from './model/guide';
export {
  guideThemes,
  OTHER_THEME,
  resolveSelection,
  searchFields,
  shortMeaning,
  themeFields,
  themeOf,
  type GuideTheme,
} from './model/themes';
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
