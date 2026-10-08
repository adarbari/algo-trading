/**
 * The edge model: the `EdgesPage` response (ADR 0053) as the page shows it. Each edge keeps what
 * the server sent; its canonical run's frozen-slice rows are picked out and ordered for display
 * (the main variant first, screeners before baselines). Pure: it chooses among served rows, it
 * never computes a figure, and an exploratory row is never among them.
 */
import type { StatusTone } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

export type EdgesResponse = gqlTypes.EdgesPageQuery;
export type ServedEdge = EdgesResponse['edges'][number];
type ServedRow = NonNullable<ServedEdge['canonicalRun']>['rows'][number];

/** The slice of a run that is the frozen period: the only one a track record reads. */
const FROZEN = 'frozen';
const MAIN = 'main';
const ROLE_ORDER = ['screener', 'baseline'];

/** One stored frozen-slice row of the canonical run: a variant at one horizon. */
export interface FrozenRow {
  key: string;
  edgeVariant: string;
  variant: string;
  role: string;
  horizonSessions: number;
  sessions: number | null;
  picks: number | null;
  hitRate: number | null;
  baseRate: number | null;
  lift: number | null;
}

export interface Edge extends ServedEdge {
  /** The canonical run's frozen rows (empty: no canonical run, or none stored for the slice). */
  frozenRows: FrozenRow[];
}

const rank = (list: readonly string[], value: string): number => {
  const index = list.indexOf(value);
  return index < 0 ? list.length : index;
};

function toRow(row: ServedRow): FrozenRow {
  return {
    key: `${row.edgeVariant}/${row.role}/${row.variant}/${String(row.horizonSessions)}`,
    edgeVariant: row.edgeVariant,
    variant: row.variant,
    role: row.role,
    horizonSessions: row.horizonSessions,
    sessions: row.sessions ?? null,
    picks: row.picks ?? null,
    hitRate: row.hitRate ?? null,
    baseRate: row.baseRate ?? null,
    lift: row.lift ?? null,
  };
}

/** The frozen, non-exploratory rows of an edge's canonical run, in display order. */
export function frozenRows(edge: ServedEdge): FrozenRow[] {
  const rows = edge.canonicalRun?.rows ?? [];
  return rows
    .filter((r) => r.sliceKind === FROZEN && !r.exploratory)
    .map(toRow)
    .sort(
      (a, b) =>
        Number(b.edgeVariant === MAIN) - Number(a.edgeVariant === MAIN) ||
        a.edgeVariant.localeCompare(b.edgeVariant) ||
        rank(ROLE_ORDER, a.role) - rank(ROLE_ORDER, b.role) ||
        a.variant.localeCompare(b.variant) ||
        a.horizonSessions - b.horizonSessions,
    );
}

export function toEdges(data: EdgesResponse): Edge[] {
  return data.edges.map((edge) => ({ ...edge, frozenRows: frozenRows(edge) }));
}

/** An edge status as the list words it ("candidate" to "Candidate"). */
export function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

const TONES: Record<string, StatusTone> = {
  evidenced: 'positive',
  live: 'positive',
  candidate: 'info',
  blocked: 'warning',
  retired: 'neutral',
  rejected: 'negative',
};

export function statusTone(status: string): StatusTone {
  return TONES[status] ?? 'neutral';
}
