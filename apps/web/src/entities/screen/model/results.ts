/**
 * A screener's run as a review table (GraphQL `ScreenerRun.results`): what a page asks for
 * (the filter bar's filters, search, the catalogue columns to add, the sort, paging) and the
 * decisions a review opens on. Pure.
 */
import { toFilterInputs, type AppliedFilter } from '@/entities/filter';
import type { gqlTypes } from '@/shared/api';

/** What the review table asks the server for. */
export interface ScreenResultsQuery {
  /** The filters in force (decision, since the previous run, ranges ...), the filter bar's. */
  filters: readonly AppliedFilter[];
  q?: string | undefined;
  /** Catalogue names added as columns, in order. */
  columns: readonly string[];
  /** A column id (`rank`, `score`, `criterion:<id>`, a catalogue name ...); `-`: descending. */
  sort?: string | undefined;
  page?: number | undefined;
  size?: number | undefined;
}

/**
 * The decisions a review opens on: every pick and the picks the regime gate paused (never
 * hidden), not the rejects (about 11k rows of misses).
 */
export const DEFAULT_DECISIONS: readonly string[] = [
  'QUALIFIED',
  'WATCH',
  'LIQUIDITY_RISK',
  'EVENT_RISK',
  'PAUSED',
];

/** The operation's variables (paging only when asked: the server's defaults). */
export function resultsVariables(
  id: string,
  query: ScreenResultsQuery,
): gqlTypes.ScreenerResultsQueryVariables {
  return {
    id,
    filters: toFilterInputs(query.filters),
    q: query.q?.trim() || null,
    sort: query.sort ?? null,
    columns: [...query.columns],
    ...(query.page !== undefined ? { page: query.page } : {}),
    ...(query.size !== undefined ? { size: query.size } : {}),
  };
}

/**
 * Whether a criterion gets a column (and a line in a pick's detail): who is screened is a gate,
 * not a measurement, so a criterion on the instrument's identity (`instrument.*`) gets none.
 * The one display-column predicate of the review tables.
 */
export function isShownCriterion(criterion: { field: string }): boolean {
  return !criterion.field.startsWith('instrument.');
}
