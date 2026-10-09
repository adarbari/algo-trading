/**
 * Entity: the feature catalogue (definitions, units, formats, the site field guide's entry per
 * field: how to read it, the criterion per intent, caveats), feature distributions, how a
 * served feature value reads (format from the server, UNKNOWN reasons), the feature table
 * (instruments x catalogue columns, one page per request) and the column factories every
 * table is built from (ADR 0038).
 */
export {
  refreshCatalogue,
  useFeatureCatalogue,
  useFeatureCatalogueDetail,
  useFeatureDistribution,
} from './api/hooks';
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
  type DetailedFeature,
} from './model/catalogue';
export {
  allowsTolerance,
  coerceValue,
  fieldKind,
  opFor,
  operatorSymbol,
  operatorsFor,
  parseList,
  scaleOf,
  shapeOf,
  toStored,
  toTyped,
  type FieldKind,
  type NumberScale,
  type ToleranceUnit,
} from './model/threshold';
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
  shortMeaning,
  themeFields,
  themeOf,
  type GuideTheme,
} from './model/themes';
export {
  isUnknown,
  shownValue,
  valueFormat,
  type FeatureFormatName,
  type ServedInfo,
  type ServedValue,
} from './model/value';
export {
  distributionBins,
  distributionCategories,
  distributionMarkers,
  type FeatureDistribution,
} from './model/distribution';
