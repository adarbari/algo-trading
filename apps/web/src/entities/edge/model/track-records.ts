/**
 * The track-record model: the `ScreenerTrackRecords` response as one entry per (screener, edge)
 * with the edge's status beside it, and the record a screener shows (a list cell, a card). A record is the
 * server's frozen-period record from the edge's canonical run, never an exploratory one; this
 * only chooses among served values (the first entry, the shortest horizon).
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

/** The record the odds line reads: the first entry that ran (null: none ran). */
export function oddsEntry(entries: readonly TrackEntry[]): TrackEntry | null {
  return entries.find((e) => !e.notRun && e.horizons.length > 0) ?? null;
}

/** A screener's frozen-slice figures at its first horizon, as served (never an exploratory run). */
export interface RecordFigures {
  edgeId: string;
  edgeName: string;
  hitRate: number;
  baseRate: number;
  lift: number | null;
  sessions: number;
  horizonSessions: number;
  runLabel: string | null;
}

/**
 * The figures of the first record that ran, at its first horizon; null when none ran or the
 * hit rate, base rate and sessions are not all stored (a bare hit rate is never shown).
 */
export function recordFigures(entries: readonly TrackEntry[]): RecordFigures | null {
  const entry = oddsEntry(entries);
  const horizon = entry?.horizons[0];
  if (!entry || !horizon) return null;
  const { hitRate, baseRate, sessions } = horizon;
  if (hitRate == null || baseRate == null || sessions == null) return null;
  return {
    edgeId: entry.edgeId,
    edgeName: entry.edgeName,
    hitRate,
    baseRate,
    lift: horizon.lift ?? null,
    sessions,
    horizonSessions: horizon.horizonSessions,
    runLabel: entry.runLabel ?? null,
  };
}
