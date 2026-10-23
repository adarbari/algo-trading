/**
 * The edge context of one screener's page: its edges ordered strongest first (by status, then by
 * the trades behind the record), the first being the headline, each with its frozen-period figures
 * or the server's reason there are none. Only chooses among served values; a record is the
 * frozen-period record of the edge's canonical run, never an exploratory one (ADR 0053).
 */
import type { ServedUnknown } from '@/entities/availability';
import type { gqlTypes } from '@/shared/api';

export type ScreenerEdgesResponse = gqlTypes.ScreenerEdgesQuery;

/** One edge that lists the screener, with its record when it ran. */
export interface ScreenerEdge {
  edgeId: string;
  edgeName: string;
  /** The edge's status (candidate, evidenced, ...); null if the edge was not listed. */
  status: string | null;
  /** The first session of the frozen period the figures cover (null: not given). */
  frozenSince: string | null;
  /** The record's run, named. */
  runLabel: string | null;
  figures: {
    hitRate: number;
    baseRate: number;
    liftPts: number | null;
    /** Independent sessions behind the rates (the trades). */
    trades: number;
    picks: number | null;
    horizonSessions: number;
  } | null;
  /** Why there is no record (null: there is one, or the figures are partly not stored). */
  notRun: ServedUnknown | null;
}

/** The statuses from strongest to weakest: the order the headline edge is chosen in. */
const STATUS_ORDER = [
  'live',
  'evidenced',
  'candidate',
  'researching',
  'blocked',
  'retired',
  'rejected',
];

const strength = (status: string | null): number => {
  const at = status === null ? -1 : STATUS_ORDER.indexOf(status);
  return at === -1 ? STATUS_ORDER.length : at;
};

export function screenerEdges(data: ScreenerEdgesResponse): ScreenerEdge[] {
  const status = new Map(data.edges.map((e) => [e.id, e.status]));
  const found = (data.screener?.trackRecords ?? []).map((r): ScreenerEdge => {
    const horizon = r.horizons[0];
    const complete =
      horizon && horizon.hitRate != null && horizon.baseRate != null && horizon.sessions != null;
    return {
      edgeId: r.edgeId,
      edgeName: r.edgeName,
      status: status.get(r.edgeId) ?? null,
      frozenSince: r.splitFrom ?? null,
      runLabel: r.runLabel ?? null,
      figures:
        complete && !r.notRun
          ? {
              hitRate: horizon.hitRate as number,
              baseRate: horizon.baseRate as number,
              liftPts: horizon.liftPts ?? null,
              trades: horizon.sessions as number,
              picks: horizon.picks ?? null,
              horizonSessions: horizon.horizonSessions,
            }
          : null,
      notRun: r.notRun ?? null,
    };
  });
  return found.sort(
    (a, b) =>
      strength(a.status) - strength(b.status) ||
      (b.figures?.trades ?? 0) - (a.figures?.trades ?? 0) ||
      a.edgeId.localeCompare(b.edgeId),
  );
}
