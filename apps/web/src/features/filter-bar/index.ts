/** Feature: the shared filter bar's state, a filter list in the `f` URL search parameter. */
export { decodeFilters, encodeFilters } from './model/codec';
export { filterSearch, type FilterSearch } from './model/search';
export {
  type FilterPatch,
  type FilterState,
  type FilterUnit,
  type FilterWindow,
} from './model/state';
export { useFilterState, type FilterStateApi } from './api/use-filter-state';
