/** The ingestion entity's types, as `Query.{completeness,ingestionCell,chainCoverage,knownCoverage}` serve them. */
import type { gqlTypes } from '@/shared/api';

export type Completeness = NonNullable<gqlTypes.IngestionCompletenessQuery['completeness']>;
export type CompletenessCell = Completeness['cells'][number];
export type CellDetail = NonNullable<gqlTypes.IngestionCellQuery['ingestionCell']>;
export type ChainCoverage = NonNullable<gqlTypes.IngestionCompletenessQuery['chainCoverage']>;

export type KnownCoverage = NonNullable<gqlTypes.KnownCoverageQuery['knownCoverage']>;
export type KnownByType = KnownCoverage['byType'][number];
export type KnownGapCount = KnownCoverage['gaps'][number];

/** A cell of the grid: one dataset on one session (ISO date). */
export interface CellRef {
  dataset: string;
  session: string;
}
