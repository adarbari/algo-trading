/**
 * The widget's column plans, only from the factories (ADR 0038): the feature table's (the
 * ticker, then one feature column per catalogue column the server sent, in the order asked),
 * and a screener's results' (a stored run, or the Builder's preview: rank, ticker, decision,
 * score, each criterion that gets a column, the screen's display columns not already a
 * criterion, the catalogue columns the user added, what changed since the previous run, the
 * flags and why); how many pages a query has, and the missing tables' short names.
 */
import {
  changeColumn,
  criterionColumn,
  decisionColumn,
  featureColumn,
  flagsColumn,
  rankColumn,
  reasonsColumn,
  scoreColumn,
  screenColumn,
  tickerColumn,
  type ColumnInfo,
  type ColumnPlan,
  type CriterionInfo,
  type ScreenColumnInfo,
} from '@/entities/feature';
import { isShownCriterion } from '@/entities/screen';

export function tablePlan(columns: readonly ColumnInfo[]): ColumnPlan {
  return [tickerColumn(), ...columns.map(featureColumn)];
}

export interface ResultsPlanInput {
  criteria: readonly CriterionInfo[];
  displayColumns: readonly ScreenColumnInfo[];
  /** The catalogue columns the user added (as the server sent them). */
  added: readonly ColumnInfo[];
  /** The catalogue: formats and labels the criteria and display columns by their field. */
  catalogue: ReadonlyMap<string, ColumnInfo>;
  /** Tickers the unsaved criteria would drop from the picks. */
  leaving?: ReadonlySet<string> | undefined;
  /** A stored run: the change since the previous run gets a column. */
  changes?: boolean | undefined;
  /** A criterion's label in a score breakdown (the preview's scores open one). */
  labelOf?: ((criterionId: string, field: string) => string) | undefined;
}

export function resultsPlan({
  criteria,
  displayColumns,
  added,
  catalogue,
  leaving,
  changes = false,
  labelOf,
}: ResultsPlanInput): ColumnPlan {
  const shown = criteria.filter(isShownCriterion);
  const judged = new Set(shown.map((c) => c.field));
  return [
    rankColumn(),
    tickerColumn(),
    decisionColumn(leaving),
    scoreColumn(labelOf),
    ...shown.map((c) => criterionColumn(c, catalogue.get(c.field))),
    ...displayColumns
      .filter((c) => !judged.has(c.field))
      .map((c) => screenColumn(c, catalogue.get(c.field))),
    ...added.map(featureColumn),
    ...(changes ? [changeColumn()] : []),
    flagsColumn(),
    reasonsColumn(),
  ];
}

/** The number of pages of `total` rows, `size` per page (at least one). */
export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, size)));
}

/** The tables named in the session's `missing`, without the rollup prefix. */
export function missingTables(missing: readonly string[]): string[] {
  return missing.map((table) => table.replace(/^rollups\/instrument\//, ''));
}
