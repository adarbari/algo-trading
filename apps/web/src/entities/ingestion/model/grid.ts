/**
 * The completeness grid as the HeatGrid shows it (datasets x sessions). A cell is complete
 * (COMPLETE, or CARRIED: an earlier snapshot stands in), partial, failed (MISSING after the
 * dataset was collected on an earlier session of the window) or not collected (MISSING before
 * it ever was: e.g. option chains before the first Cboe snapshot). Its text is the share of the
 * expected rows present, where there is an expectation.
 */
import { formatValue, type HeatGridColumn, type HeatGridRow, type HeatStatus } from '@algotrade/ui';

import { datasetLabel } from './dataset';
import type { CellRef, Completeness, CompletenessCell } from './types';

export const SESSIONS = 10;

/** present / expected, or null without an expectation. */
export function cellShare(cell: CompletenessCell): number | null {
  if (cell.expected === null || cell.expected <= 0) return null;
  return Math.min(cell.present / cell.expected, 1);
}

/** The share as cell text: `100`, `99.7`, `86.2`; empty without an expectation. */
export function shareText(share: number | null): string {
  if (share === null) return '';
  if (share >= 0.9995) return '100';
  return formatValue(share * 100, { kind: 'number', digits: 1 }).text;
}

export function heatStatus(cell: CompletenessCell, collectedBefore: boolean): HeatStatus {
  switch (cell.status) {
    case 'COMPLETE':
    case 'CARRIED':
      return 'complete';
    case 'PARTIAL':
      return 'partial';
    case 'MISSING':
      return collectedBefore ? 'failed' : 'not-collected';
    default:
      return 'failed';
  }
}

/** Cells by dataset, in session order (oldest first). */
function byDataset(completeness: Completeness): Map<string, CompletenessCell[]> {
  const order = new Map(completeness.sessions.map((s, i) => [s, i]));
  const grouped = new Map<string, CompletenessCell[]>(completeness.datasets.map((d) => [d, []]));
  for (const cell of completeness.cells) grouped.get(cell.dataset)?.push(cell);
  for (const cells of grouped.values()) {
    cells.sort((a, b) => (order.get(a.session) ?? 0) - (order.get(b.session) ?? 0));
  }
  return grouped;
}

/** Each cell's grid status (`dataset|session` -> status). */
export function cellStatuses(completeness: Completeness): Map<string, HeatStatus> {
  const statuses = new Map<string, HeatStatus>();
  for (const [dataset, cells] of byDataset(completeness)) {
    let collected = false;
    for (const cell of cells) {
      statuses.set(`${dataset}|${cell.session}`, heatStatus(cell, collected));
      collected ||= cell.status !== 'MISSING';
    }
  }
  return statuses;
}

/** Session headers: `21 Sept`, then `Tue 22` ... until the month changes (`1 Oct`). */
export function gridColumns(completeness: Completeness): HeatGridColumn[] {
  return completeness.sessions.map((s, i) => {
    const [weekday = '', day = '', month = ''] = formatValue(s, {
      kind: 'date',
      style: 'weekday',
    }).text.split(' ');
    const sameMonth = i > 0 && completeness.sessions[i - 1]?.slice(0, 7) === s.slice(0, 7);
    return { id: s, label: sameMonth ? `${weekday} ${day}` : `${day} ${month}` };
  });
}

export function gridRows(completeness: Completeness): HeatGridRow[] {
  const statuses = cellStatuses(completeness);
  return [...byDataset(completeness)].map(([dataset, cells]) => ({
    id: dataset,
    label: datasetLabel(dataset),
    cells: Object.fromEntries(
      cells.map((c) => [
        c.session,
        {
          status: statuses.get(`${dataset}|${c.session}`) ?? 'not-collected',
          text: c.status === 'MISSING' ? '' : shareText(cellShare(c)),
        },
      ]),
    ),
  }));
}

const PRIORITY: Record<HeatStatus, number> = {
  failed: 0,
  partial: 1,
  complete: 2,
  'not-collected': 3,
};

/** The cell to drill into first: the latest session's worst cell (first dataset on ties). */
export function defaultCell(completeness: Completeness): CellRef | null {
  const latest = completeness.sessions.at(-1);
  if (!latest) return null;
  const statuses = cellStatuses(completeness);
  const candidates = completeness.datasets.map((dataset) => ({
    dataset,
    rank: PRIORITY[statuses.get(`${dataset}|${latest}`) ?? 'not-collected'],
  }));
  const [best] = [...candidates].sort((a, b) => a.rank - b.rank);
  return best ? { dataset: best.dataset, session: latest } : null;
}

/** The cell of the grid at `ref`, if the window has it. */
export function findCell(completeness: Completeness, ref: CellRef): CompletenessCell | undefined {
  return completeness.cells.find((c) => c.dataset === ref.dataset && c.session === ref.session);
}
