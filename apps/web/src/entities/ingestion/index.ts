/** Entity: ingestion completeness (dataset x session grid, a cell's drill-down, option-chain coverage). */
export {
  prefetchCompleteness,
  useCellDetail,
  useChainCoverage,
  useCompleteness,
  useFocusCell,
} from './api/queries';
export { useKnownCoverage } from './api/known';
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
export type {
  CellDetail,
  CellRef,
  ChainCoverage,
  Completeness,
  CompletenessCell,
  KnownByType,
  KnownCoverage,
  KnownGapCount,
} from './model/types';
