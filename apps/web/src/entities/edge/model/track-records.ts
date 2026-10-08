/**
 * The track-record model: the `ScreenerTrackRecords` response as one entry per (screener, edge)
 * with the edge's status beside it, and the chip and odds line a screener shows. A record is the
 * server's frozen-period record from the edge's canonical run, never an exploratory one; this
 * only chooses among served values (the first entry, the shortest horizon).
 */
import type { TrackRecordStatus } from '@algotrade/ui';

import type { ServedUnknown } from '@/entities/availability';
import type { gqlTypes } from '@/shared/api';

export type TrackRecordsResponse = gqlTypes.ScreenerTrackRecordsQuery;
type ServedRecord = TrackRecordsResponse['screeners'][number]['trackRecords'][number];

export interface TrackEntry extends Omit<ServedRecord, 'notRun'> {
  /** The edge's status (candidate, evidenced, ...), or null if the edge was not listed. */
  edgeStatus: string | null;
  notRun: ServedUnknown | null;
}

/** What the chip shows for a screener: its first edge's state and how many more edges list it. */
export interface Chip {
  status: TrackRecordStatus;
  sessions?: number;
  more: number;
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

/**
 * The chip of a screener's first record: not run, evidenced (an evidenced or live edge) or a
 * candidate with its independent sessions so far. A retired, rejected or blocked edge shows none.
 */
export function chipOf(entries: readonly TrackEntry[]): Chip | null {
  const first = entries[0];
  if (!first) return null;
  const more = entries.length - 1;
  if (first.notRun) return { status: 'not-run', more };
  if (first.edgeStatus === 'evidenced' || first.edgeStatus === 'live') {
    return { status: 'evidenced', more };
  }
  if (first.edgeStatus === 'candidate') {
    const sessions = first.horizons[0]?.sessions;
    return { status: 'candidate', ...(sessions == null ? {} : { sessions }), more };
  }
  return null;
}

/** The record the odds line reads: the first entry that ran (null: none ran). */
export function oddsEntry(entries: readonly TrackEntry[]): TrackEntry | null {
  return entries.find((e) => !e.notRun && e.horizons.length > 0) ?? null;
}
