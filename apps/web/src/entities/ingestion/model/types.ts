/** The ingestion entity's types, as `Query.{completeness,ingestionCell}` serve them. */
import type { gqlTypes } from '@/shared/api';

export type Completeness = NonNullable<gqlTypes.IngestionCompletenessQuery['completeness']>;
export type CompletenessCell = Completeness['cells'][number];
export type CellDetail = NonNullable<gqlTypes.IngestionCellQuery['ingestionCell']>;

/** A cell of the grid: one dataset on one session (ISO date). */
export interface CellRef {
  dataset: string;
  session: string;
}
