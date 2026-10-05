/**
 * A rule screen's latest run as a review table (GET /screens/{id}/table): the rows with their
 * decision, criteria, display columns and features, the counts per decision and the changes
 * since the previous run, and the user's saved view of it (columns, sort, decisions). Pure.
 */
import type { components } from '@/shared/api';

export type ScreenTable = components['schemas']['ScreenTable'];
export type ScreenTableRow = components['schemas']['ScreenTableRow'];
export type CriterionHeader = components['schemas']['CriterionHeader'];
export type ScreenerView = components['schemas']['ScreenerView'];

export type ScreenChange = 'new' | 'dropped';

/** What the table asks for: filters, the catalogue features to add, the sort. */
export interface ScreenTableQuery {
  decisions: readonly string[];
  change?: ScreenChange | undefined;
  q?: string | undefined;
  columns: readonly string[];
  sort?: string | undefined;
}

/** The decisions a review opens on: every pick, not the rejects (about 11k rows of misses). */
export const DEFAULT_DECISIONS: readonly string[] = [
  'QUALIFIED',
  'WATCH',
  'LIQUIDITY_RISK',
  'EVENT_RISK',
];

/** The most rows one request returns (the API's page size limit). */
export const TABLE_ROWS = 1000;

/** The GET query for a table query. */
export function tableParams(query: ScreenTableQuery) {
  return {
    decision: query.decisions.length > 0 ? query.decisions.join(',') : null,
    change: query.change ?? null,
    q: query.q?.trim() || null,
    columns: query.columns.length > 0 ? query.columns.join(',') : null,
    sort: query.sort ?? null,
    size: TABLE_ROWS,
  };
}

/** The decisions to show: the saved ones, else the defaults. */
export function shownDecisions(view: ScreenerView | undefined): readonly string[] {
  return view?.saved && view.decisions.length > 0 ? view.decisions : DEFAULT_DECISIONS;
}

/** The decisions of a run in display order (picks first, rejects last), with their counts. */
export function orderedDecisions(counts: Readonly<Record<string, number>>) {
  const order = [...DEFAULT_DECISIONS, 'UNKNOWN', 'REJECT', 'SKIPPED'];
  const rank = (decision: string) => {
    const i = order.indexOf(decision);
    return i < 0 ? order.length : i;
  };
  return Object.entries(counts)
    .filter(([, count]) => count > 0)
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([decision, count]) => ({ decision, count }));
}
