/**
 * The run entity's types, as the GraphQL operations serve them (`Query.{nightlyRuns,run,
 * runItems,quality}`); a run record's open-ended JSON (`itemsByStatus`, `stats`) is narrowed to
 * records once, in `model/run.ts`.
 */
import type { gqlTypes } from '@/shared/api';

type ServedRun = NonNullable<gqlTypes.RunRecordQuery['run']>;

export type NightlyRun = gqlTypes.NightlyRunsQuery['nightlyRuns'][number];
export type RunStep = NightlyRun['steps'][number];
export type FailureGroup = ServedRun['failures'][number];
export type RunItem = NonNullable<gqlTypes.RunItemsQuery['runItems']>[number];
export type QualityReport = NonNullable<gqlTypes.QualityChecksQuery['quality']>;
export type QualityCheck = QualityReport['checks'][number];

/** A run record as served (the drill-down's `IngestionCell.runs` select the same fields). */
export type ServedRunDetail = ServedRun;

/** One run record: items per status code (most common first) and its stats as recorded. */
export interface RunDetail extends Omit<ServedRunDetail, 'itemsByStatus' | 'stats'> {
  itemsByStatus: Readonly<Record<string, number>>;
  stats: Readonly<Record<string, unknown>>;
}
