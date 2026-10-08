/**
 * A screener's result rows as the table's `TableRow`s: a stored run's page (GraphQL
 * `ScreenerRun.results`: each result with its catalogue cells, columnar as a feature table) and
 * the Builder's preview rows (the preview POST, shaped the same way). Pure.
 */
import type { ColumnInfo, TableCell, TableRow } from '@/entities/feature';
import type { PreviewRow, ScreenerResultsResponse } from '@/entities/screen';

type Run = NonNullable<NonNullable<ScreenerResultsResponse['screener']>['latestRun']>;
export type ResultsPage = Run['results'];

/** The page's results with their cells (`rows[i][j]` is `columns[j]` for `results[i]`). */
export function resultRows(page: ResultsPage): TableRow[] {
  return page.results.map((result, i) => {
    const values = page.rows[i] ?? [];
    const codes = page.unknown[i] ?? [];
    const reasons = page.reasons[i] ?? [];
    const kinds = page.kinds[i] ?? [];
    const texts = new Map(page.kindTexts.map((t) => [t.kind, t.text]));
    const cells: Record<string, TableCell> = {};
    page.columns.forEach((column: ColumnInfo, j) => {
      cells[column.name] = {
        value: values[j] ?? null,
        unknown: codes[j] ?? null,
        reason: reasons[j] ?? null,
        kind: kinds[j] ?? null,
        kindText: (kinds[j] && texts.get(kinds[j])) || null,
      };
    });
    return {
      symbol: result.instrument?.symbol ?? result.instrumentId,
      instrumentId: result.instrumentId,
      name: result.instrument?.name ?? '',
      cells,
      rank: result.rank,
      decision: result.decision,
      score: result.score ?? null,
      flags: result.flags,
      criteria: Object.fromEntries(
        result.criteria.map((c) => [c.id, { value: c.value, outcome: c.outcome }]),
      ),
      change: result.change ?? null,
      previousDecision: result.previousDecision ?? null,
      columns: Object.fromEntries(result.columns.map((c) => [c.name, c.value])),
      reasons: result.reasons,
    };
  });
}

/** The preview's rows (no catalogue cells: the preview reads what the screen reads). */
export function previewRows(rows: readonly PreviewRow[]): TableRow[] {
  return rows.map((row) => ({
    symbol: row.symbol ?? row.instrument_id,
    instrumentId: row.instrument_id,
    name: row.name ?? '',
    cells: {},
    rank: row.rank,
    decision: row.decision,
    score: row.score,
    flags: row.flags,
    criteria: Object.fromEntries(
      row.criteria.map((c) => [c.criterion_id, { value: c.value, outcome: c.outcome }]),
    ),
    columns: row.columns,
    reasons: row.reasons.join('; '),
    scoring: row,
  }));
}
