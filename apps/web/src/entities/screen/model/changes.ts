/**
 * What an edit would change: the picks of the live preview of unsaved criteria against the picks
 * of the saved run. A ticker is *picked* when its decision is not REJECT, SKIPPED or UNKNOWN (as
 * in Ideas and the results' New / Dropped). The preview lists only its top rows, so a long list
 * of picks is compared by what it shows. Pure.
 */

const NOT_PICKED: ReadonlySet<string> = new Set(['REJECT', 'SKIPPED', 'UNKNOWN']);

export interface PickedRow {
  symbol: string | null;
  decision: string;
}

export interface PreviewChanges {
  /** Picked by the unsaved criteria, not by the saved run. */
  enter: string[];
  /** Picked by the saved run, not by the unsaved criteria. */
  exit: string[];
}

const picked = (rows: readonly PickedRow[]): Set<string> =>
  new Set(
    rows.flatMap((row) =>
      row.symbol !== null && !NOT_PICKED.has(row.decision) ? [row.symbol] : [],
    ),
  );

export function previewChanges(
  saved: readonly PickedRow[],
  preview: readonly PickedRow[],
): PreviewChanges {
  const before = picked(saved);
  const after = picked(preview);
  return {
    enter: [...after].filter((symbol) => !before.has(symbol)).sort(),
    exit: [...before].filter((symbol) => !after.has(symbol)).sort(),
  };
}
