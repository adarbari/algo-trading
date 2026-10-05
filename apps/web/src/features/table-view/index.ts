/**
 * Feature: a user's saved views of a table (read model WEB 7: the one view-preferences
 * adapter). `useTableView(scope)` holds the view in use and saves every change; `ViewControls`
 * switches, names and removes views.
 */
export { TABLE_VIEW_OPERATION, type SavedView } from './api/views';
export { useTableView, type TableViewState } from './model/table-view';
export { formatSort, parseSort, screenerScope, type ViewContent } from './model/view';
export { ViewControls, type ViewControlsProps } from './ui/ViewControls';
