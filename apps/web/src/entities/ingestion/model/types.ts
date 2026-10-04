/** The ingestion entity's types: the completeness grid and one cell's drill-down. */
import type { components } from '@/shared/api';

type Schemas = components['schemas'];

export type Completeness = Schemas['Completeness'];
export type CompletenessCell = Schemas['Cell'];
export type CellDetail = Schemas['CellDetail'];

/** A cell of the grid: one dataset on one session (ISO date). */
export interface CellRef {
  dataset: string;
  session: string;
}
