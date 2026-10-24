/**
 * The Screeners list's rows: the user's own screeners and the site presets as one list, each with
 * its kind, and the narrowing the server answered for the filters and the search. Pure; it chooses
 * among served rows and derives nothing from run data.
 */
import type { ScreenerListItem, ScreenerSummary } from '@/entities/screen';

export interface ListRow {
  id: string;
  kind: 'mine' | 'preset';
  /** A rule screener (opens in the Builder and shows its criteria); else Python code. */
  rules: boolean;
  /** Mine: not finalized yet (it has no run). */
  draft: boolean;
  /** Mine: the preset it was copied from. */
  presetId: string | null;
  /** Mine: its config does not resolve (the server's words). */
  error: string | null;
}

/** Your screeners first (by name), then the presets (by name). */
export function toRows(
  configs: readonly ScreenerSummary[],
  mine: readonly ScreenerListItem[],
): ListRow[] {
  const resolved = new Map(configs.filter((c) => c.scope !== 'site').map((c) => [c.configId, c]));
  const own: ListRow[] = mine.map((s) => ({
    id: s.screenerId,
    kind: 'mine',
    rules: true,
    draft: s.status === 'DRAFT',
    presetId: s.presetId ?? null,
    error: resolved.get(s.screenerId)?.error ?? null,
  }));
  const presets: ListRow[] = configs
    .filter((c) => c.scope === 'site')
    .map((c) => ({
      id: c.configId,
      kind: 'preset',
      rules: c.impl === 'rules',
      draft: false,
      presetId: null,
      error: null,
    }));
  const byId = (a: ListRow, b: ListRow) => a.id.localeCompare(b.id);
  return [...own.sort(byId), ...presets.sort(byId)];
}

/**
 * The rows the server's narrowing keeps. With none in force (`ids` null) every row stays,
 * drafts and screeners that do not resolve included; with one, only the ids it names (a draft has
 * no facts to filter on, so none passes).
 */
export function narrowRows(rows: readonly ListRow[], ids: ReadonlySet<string> | null): ListRow[] {
  return ids === null ? [...rows] : rows.filter((row) => ids.has(row.id));
}
