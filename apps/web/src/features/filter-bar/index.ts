/** Feature: the shared filter bar: URL state (`f`) and `SurfaceFilterBar`, one component for any surface (ADR 0082). */
export { decodeFilters, encodeFilters } from './model/codec';
export { filterSearch, type FilterSearch } from './model/search';
export {
  type FilterPatch,
  type FilterState,
  type FilterUnit,
  type FilterWindow,
} from './model/state';
export { useFilterState, type FilterStateApi } from './api/use-filter-state';
export {
  parseGuideRef,
  SurfaceFilterBar,
  type GuideRef,
  type SurfaceFilterBarProps,
} from './ui/SurfaceFilterBar';
export { type LabelOf } from './model/surface';
export { SurfaceZeroResults, type SurfaceZeroResultsProps } from './ui/SurfaceZeroResults';
