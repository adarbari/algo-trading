/** Entity: the feature catalogue (definitions, units, formats) and feature distributions. */
export { useFeatureCatalogue, useFeatureDistribution } from './api/hooks';
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
  distributionBins,
  distributionCategories,
  distributionMarkers,
  type FeatureDistribution,
} from './model/distribution';
