/**
 * A screener's run as a review table (GraphQL `ScreenerRun.results`): what a page asks for
 * (decisions, change, search, the catalogue columns to add, the sort, paging), the decisions a
 * review opens on, and the run's decision counts in display order. Pure.
 */
import type { gqlTypes } from '@/shared/api';

export type ScreenChange = 'new' | 'dropped';

/** What the review table asks the server for. */
export interface ScreenResultsQuery {
  decisions: readonly string[];
  change?: ScreenChange | undefined;
  q?: string | undefined;
  /** Catalogue names added as columns, in order. */
  columns: readonly string[];
  /** A column id (`rank`, `score`, `criterion:<id>`, a catalogue name ...); `-`: descending. */
  sort?: string | undefined;
  page?: number | undefined;
  size?: number | undefined;
}

/** The decisions a review opens on: every pick, not the rejects (about 11k rows of misses). */
export const DEFAULT_DECISIONS: readonly string[] = [
  'QUALIFIED',
  'WATCH',
  'LIQUIDITY_RISK',
  'EVENT_RISK',
];

/** The operation's variables (paging only when asked: the server's defaults). */
export function resultsVariables(
  id: string,
  query: ScreenResultsQuery,
): gqlTypes.ScreenerResultsQueryVariables {
  return {
    id,
    decisions: query.decisions.length > 0 ? [...query.decisions] : null,
    change: query.change ?? null,
    q: query.q?.trim() || null,
    sort: query.sort ?? null,
    columns: [...query.columns],
    ...(query.page !== undefined ? { page: query.page } : {}),
    ...(query.size !== undefined ? { size: query.size } : {}),
  };
}

/** The decisions to show: the saved ones, else the picks. */
export function shownDecisions(
  view: { saved: boolean; decisions: readonly string[] } | null | undefined,
): readonly string[] {
  return view?.saved && view.decisions.length > 0 ? view.decisions : DEFAULT_DECISIONS;
}

/** The decisions of a run in display order (picks first, rejects last), with their counts. */
export function orderedDecisions(counts: readonly { decision: string; count: number }[]) {
  const order = [...DEFAULT_DECISIONS, 'UNKNOWN', 'REJECT', 'SKIPPED'];
  const rank = (decision: string) => {
    const i = order.indexOf(decision);
    return i < 0 ? order.length : i;
  };
  return counts
    .filter(({ count }) => count > 0)
    .sort((a, b) => rank(a.decision) - rank(b.decision) || a.decision.localeCompare(b.decision));
}

/**
 * Whether a criterion gets a column (and a line in a pick's detail): who is screened is a gate,
 * not a measurement, so a criterion on the instrument's identity (`instrument.*`) gets none.
 * The one display-column predicate of the review tables.
 */
export function isShownCriterion(criterion: { field: string }): boolean {
  return !criterion.field.startsWith('instrument.');
}
