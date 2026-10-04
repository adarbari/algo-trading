/** Entity: ingestion completeness (dataset x session grid, a cell's drill-down). */
export { useCellDetail, useCompleteness, useFocusCell } from './api/queries';
export { datasetLabel, isChains } from './model/dataset';
export {
  cellShare,
  defaultCell,
  findCell,
  gridColumns,
  gridRows,
  SESSIONS,
  shareText,
} from './model/grid';
export { completenessSummary, staleSince, type CompletenessSummary } from './model/summary';
export type { CellDetail, CellRef, Completeness, CompletenessCell } from './model/types';
