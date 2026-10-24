/**
 * Entity: a user's saved views of a table (read model WEB 7: the one view-preferences adapter).
 * `useTableView(scope)` holds the view in use and saves every change; a scope names the table:
 * `screenerScope(id)` a screener's results, `surfaceScope(name)` a list with a filter bar
 * (ADR 0082). The shared filter bar's Views menu (`features/filter-bar`) lists, applies, saves and
 * deletes them.
 */
export { TABLE_VIEW_OPERATION, useSavedView, type SavedView } from './api/views';
export { useTableView, type FilterBinding, type TableViewState } from './model/table-view';
export {
  formatSort,
  parseSort,
  restorableFilters,
  screenerScope,
  surfaceScope,
  type ViewContent,
} from './model/view';
