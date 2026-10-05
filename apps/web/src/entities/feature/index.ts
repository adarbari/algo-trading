/**
 * Entity: the feature catalogue (definitions, units, formats), feature distributions, and how
 * a served feature value reads (format from the server, UNKNOWN reasons).
 */
export { refreshCatalogue, useFeatureCatalogue, useFeatureDistribution } from './api/hooks';
export {
  byName,
  displayValue,
  featureColumn,
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
  isUnknown,
  shownValue,
  unknownReason,
  valueFormat,
  type FeatureFormatName,
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
