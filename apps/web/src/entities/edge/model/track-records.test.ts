import { describe, expect, it } from 'vitest';

import { TRACK_RECORDS_FIXTURE } from './fixtures';
import { chipOf, oddsEntry, toTrackRecords, type TrackEntry } from './track-records';

const records = toTrackRecords(TRACK_RECORDS_FIXTURE);
const of = (id: string) => records.get(id) ?? [];

describe('chipOf', () => {
  it('shows the first edge: a candidate with its sessions, and how many more list it', () => {
    expect(chipOf(of('momentum_12_1'))).toEqual({ status: 'candidate', sessions: 120, more: 1 });
  });

  it('shows not-run when the edge has no canonical run', () => {
    expect(chipOf(of('vrp_scanner'))).toEqual({ status: 'not-run', more: 0 });
  });

  it('shows nothing when no edge lists the screener, or its edge is not candidate or evidenced', () => {
    expect(chipOf(of('plain'))).toBeNull();
    const entry = of('momentum_12_1')[0] as TrackEntry;
    expect(chipOf([{ ...entry, edgeStatus: 'rejected' }])).toBeNull();
    expect(chipOf([{ ...entry, edgeStatus: 'live' }])?.status).toBe('evidenced');
  });
});

describe('oddsEntry', () => {
  it('is the first record that ran, none when no edge ran', () => {
    expect(oddsEntry(of('momentum_12_1'))?.edgeId).toBe('momentum_12_1');
    expect(oddsEntry(of('vrp_scanner'))).toBeNull();
  });
});
