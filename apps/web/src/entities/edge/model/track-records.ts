/**
 * The track-record model: the `ScreenerTrackRecords` response as one entry per (screener, edge)
 * with the edge's status beside it, and the record a screener shows (a list cell, a card). A record is the
 * server's frozen-period record from the edge's canonical run, never an exploratory one; this
 * only chooses among served values (the strongest edge's record by status, then trades, then
 * id; the shortest horizon) and never computes one.
 */
import type { ServedUnknown } from '@/entities/availability';
import type { gqlTypes } from '@/shared/api';

export type TrackRecordsResponse = gqlTypes.ScreenerTrackRecordsQuery;
type ServedRecord = TrackRecordsResponse['screeners'][number]['trackRecords'][number];

export interface TrackEntry extends Omit<ServedRecord, 'notRun'> {
  /** The edge's status (candidate, evidenced, ...), or null if the edge was not listed. */
  edgeStatus: string | null;
  notRun: ServedUnknown | null;
}

export function toTrackRecords(data: TrackRecordsResponse): Map<string, TrackEntry[]> {
  const status = new Map(data.edges.map((e) => [e.id, e.status]));
  return new Map(
    data.screeners.map((s) => [
      s.id,
      s.trackRecords.map((r) => ({
        ...r,
        notRun: r.notRun ?? null,
        edgeStatus: status.get(r.edgeId) ?? null,
      })),
    ]),
  );
}

/** Fewer independent trades than this since the freeze is too few to read a record from. */
export const MIN_TRADES = 20;

/** Evidenced beats candidate beats every other status. */
const STATUS_RANK: Record<string, number> = { evidenced: 0, candidate: 1 };
const statusRank = (status: string | null): number => STATUS_RANK[status ?? ''] ?? 2;

/** A screener's frozen-slice figures at its first horizon, as served (never an exploratory run). */
export interface RecordFigures {
  edgeId: string;
  edgeName: string;
  /** The edge's status, or null if the edge was not listed. */
  edgeStatus: string | null;
  hitRate: number;
  baseRate: number;
  /** Win rate minus base rate, in points, as served. */
  liftPts: number | null;
  sessions: number;
  horizonSessions: number;
  runLabel: string | null;
  /** The date the frozen period starts (the freeze), or null if not served. */
  frozenFrom: string | null;
}

function figuresOf(entry: TrackEntry): RecordFigures | null {
  const horizon = entry.horizons[0];
  if (entry.notRun || !horizon) return null;
  const { hitRate, baseRate, sessions } = horizon;
  if (hitRate == null || baseRate == null || sessions == null) return null;
  return {
    edgeId: entry.edgeId,
    edgeName: entry.edgeName,
    edgeStatus: entry.edgeStatus,
    hitRate,
    baseRate,
    liftPts: horizon.liftPts ?? null,
    sessions,
    horizonSessions: horizon.horizonSessions,
    runLabel: entry.runLabel ?? null,
    frozenFrom: entry.splitFrom ?? null,
  };
}

/**
 * One edge's record on a screener: `record` (figures, enough trades), `few` (figures from fewer
 * than MIN_TRADES trades: no record yet), `partial` (a run whose hit rate, base rate or trades
 * are not all stored) or `none` (no canonical frozen run; `notRun` is the server's reason).
 */
export interface EdgeRecord {
  edgeId: string;
  edgeName: string;
  edgeStatus: string | null;
  state: 'record' | 'few' | 'partial' | 'none';
  figures: RecordFigures | null;
  notRun: ServedUnknown | null;
  frozenFrom: string | null;
}

function edgeRecord(entry: TrackEntry): EdgeRecord {
  const figures = figuresOf(entry);
  const ran = !entry.notRun && entry.horizons.length > 0;
  return {
    edgeId: entry.edgeId,
    edgeName: entry.edgeName,
    edgeStatus: entry.edgeStatus,
    state: figures ? (figures.sessions < MIN_TRADES ? 'few' : 'record') : ran ? 'partial' : 'none',
    figures,
    notRun: entry.notRun,
    frozenFrom: entry.splitFrom ?? null,
  };
}

const STATE_RANK = { record: 0, few: 1, partial: 2, none: 3 } as const;

/**
 * A screener's edges, strongest first: a readable record before a thin one, then status
 * (evidenced > candidate > the rest), then trades (most first), then edge id.
 */
export function rankedRecords(entries: readonly TrackEntry[]): EdgeRecord[] {
  return entries
    .map(edgeRecord)
    .sort(
      (a, b) =>
        STATE_RANK[a.state] - STATE_RANK[b.state] ||
        statusRank(a.edgeStatus) - statusRank(b.edgeStatus) ||
        (b.figures?.sessions ?? -1) - (a.figures?.sessions ?? -1) ||
        a.edgeId.localeCompare(b.edgeId),
    );
}

/** The record the odds line reads: the strongest edge's entry that ran (null: none ran). */
export function oddsEntry(entries: readonly TrackEntry[]): TrackEntry | null {
  const best = rankedRecords(entries).find((r) => r.figures);
  return entries.find((e) => e.edgeId === best?.edgeId) ?? null;
}

/**
 * The figures of the strongest record that ran, at its first horizon; null when none ran or the
 * hit rate, base rate and sessions are not all stored (a bare hit rate is never shown).
 */
export function recordFigures(entries: readonly TrackEntry[]): RecordFigures | null {
  return rankedRecords(entries).find((r) => r.figures)?.figures ?? null;
}

/** The Screeners list's evidence cell: what it says, and the edges it opens to. */
export type ScreenerEvidence =
  | { kind: 'no-edge' }
  | { kind: 'record'; headline: RecordFigures; edges: EdgeRecord[] }
  | { kind: 'pending'; why: EdgeRecord; edges: EdgeRecord[] };

export function screenerEvidence(entries: readonly TrackEntry[]): ScreenerEvidence {
  const edges = rankedRecords(entries);
  const [first] = edges;
  if (!first) return { kind: 'no-edge' };
  if (first.state === 'record' && first.figures) {
    return { kind: 'record', headline: first.figures, edges };
  }
  return { kind: 'pending', why: first, edges };
}
