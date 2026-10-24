/**
 * Entity: the shared filter bar's server side (ADR 0082): the definitions of a surface's filters
 * (`useFilterSet`), the counts served with a filtered list (`FilterFacets`) and the `filters`
 * argument a list read takes (`toFilterInputs`).
 */
export {
  FILTER_SET_OPERATION,
  prefetchFilterSet,
  useFilterFeatures,
  useFilterSet,
} from './api/hooks';
export {
  FEATURE_FILTER_PREFIX,
  FILTER_GROUPS,
  toFilterInputs,
  type AppliedFilter,
  type FilterDefinition,
  type FilterFacets,
  type FilterGroup,
  type FilterInput,
  type FilterableFeature,
  type FilterKind,
  type FilterSetResponse,
} from './model/filter';
