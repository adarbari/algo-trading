/**
 * The feature table widget's column plan and paging: the ticker, then one factory column per
 * catalogue column the server sent (in the order asked); the page a query shows (back to the
 * first whenever the query changes) and how many pages it has.
 */
import { featureColumn, tickerColumn, type ColumnInfo, type ColumnPlan } from '@/entities/feature';

export function tablePlan(columns: readonly ColumnInfo[]): ColumnPlan {
  return [tickerColumn(), ...columns.map(featureColumn)];
}

/** The number of pages of `total` rows, `size` per page (at least one). */
export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, size)));
}

/** The tables named in the session's `missing`, without the rollup prefix. */
export function missingTables(missing: readonly string[]): string[] {
  return missing.map((table) => table.replace(/^rollups\/instrument\//, ''));
}
