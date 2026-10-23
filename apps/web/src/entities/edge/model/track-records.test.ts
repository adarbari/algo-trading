import { describe, expect, it } from 'vitest';

import { TRACK_RECORDS_FIXTURE } from './fixtures';
import {
  oddsEntry,
  rankedRecords,
  recordFigures,
  screenerEvidence,
  toTrackRecords,
  type TrackEntry,
} from './track-records';

const records = toTrackRecords(TRACK_RECORDS_FIXTURE);
const of = (id: string) => records.get(id) ?? [];

const entry = (
  edgeId: string,
  edgeStatus: string | null,
  sessions: number | null,
  patch: Partial<TrackEntry> = {},
): TrackEntry => ({
  screenerId: 's',
  edgeId,
  edgeName: `Edge ${edgeId}`,
  edgeStatus,
  runLabel: null,
  splitFrom: '2026-04-01',
  afterSession: false,
  notRun: null,
  horizons:
    sessions === null
      ? []
      : [
          {
            horizonSessions: 21,
            hitRate: 0.6,
            baseRate: 0.5,
            liftPts: 10,
            sessions,
            picks: 100,
          },
        ],
  ...patch,
});

describe('headline edge selection (two edges on one screener: the first no longer wins)', () => {
  it('prefers an evidenced edge to a candidate that is listed first', () => {
    const entries = [entry('a_candidate', 'candidate', 200), entry('b_evidenced', 'evidenced', 40)];
    expect(rankedRecords(entries)[0]?.edgeId).toBe('b_evidenced');
    expect(oddsEntry(entries)?.edgeId).toBe('b_evidenced');
  });

  it('prefers candidate to other statuses, then more trades, then edge id', () => {
    expect(
      rankedRecords([entry('z', 'researching', 90), entry('y', 'candidate', 30)])[0]?.edgeId,
    ).toBe('y');
    expect(
      rankedRecords([entry('a', 'candidate', 30), entry('b', 'candidate', 80)])[0]?.edgeId,
    ).toBe('b');
    expect(
      rankedRecords([entry('b', 'candidate', 50), entry('a', 'candidate', 50)])[0]?.edgeId,
    ).toBe('a');
  });

  it('puts an edge with a readable record before a stronger status without one', () => {
    const entries = [entry('ev', 'evidenced', 5), entry('cand', 'candidate', 60)];
    expect(rankedRecords(entries).map((r) => r.edgeId)).toEqual(['cand', 'ev']);
  });

  it('reads the fixture screener in two edges as the evidenced one', () => {
    expect(oddsEntry(of('momentum_12_1'))?.edgeId).toBe('earnings_drift');
    expect(oddsEntry(of('vrp_scanner'))).toBeNull();
  });
});

describe('recordFigures', () => {
  it('reads the first horizon of the strongest record that ran, with the freeze date', () => {
    expect(recordFigures(of('momentum_12_1'))).toMatchObject({
      edgeId: 'earnings_drift',
      edgeStatus: 'evidenced',
      hitRate: 0.58,
      baseRate: 0.51,
      sessions: 80,
      frozenFrom: '2026-05-01',
    });
  });

  it('is null when no edge ran or lists it', () => {
    expect(recordFigures(of('vrp_scanner'))).toBeNull();
    expect(recordFigures(of('plain'))).toBeNull();
  });

  it('is null when the hit rate is not stored: a bare number is never shown', () => {
    const e = entry('a', 'candidate', 40);
    const partial = { ...e, horizons: [{ ...e.horizons[0], hitRate: null }] } as TrackEntry;
    expect(recordFigures([partial])).toBeNull();
  });
});

describe('screenerEvidence', () => {
  it('is no-edge for a screener in no edge', () => {
    expect(screenerEvidence(of('plain'))).toEqual({ kind: 'no-edge' });
  });

  it('is a record with every edge, headline first', () => {
    const evidence = screenerEvidence(of('momentum_12_1'));
    expect(evidence.kind).toBe('record');
    if (evidence.kind === 'record') {
      expect(evidence.headline.edgeId).toBe('earnings_drift');
      expect(evidence.edges.map((e) => e.edgeId)).toEqual(['earnings_drift', 'momentum_12_1']);
    }
  });

  it('is pending with the server reason when the edge has no frozen run', () => {
    const evidence = screenerEvidence(of('vrp_scanner'));
    expect(evidence.kind).toBe('pending');
    if (evidence.kind === 'pending') {
      expect(evidence.why.state).toBe('none');
      expect(evidence.why.notRun?.kindText).toBe('not run yet');
    }
  });

  it('is pending, "few", under 20 trades since the freeze', () => {
    const evidence = screenerEvidence([entry('a', 'candidate', 12)]);
    expect(evidence.kind).toBe('pending');
    if (evidence.kind === 'pending') expect(evidence.why.state).toBe('few');
  });

  it('is pending, partial, for a run with a missing figure', () => {
    const e = entry('a', 'candidate', 40);
    const partial = { ...e, horizons: [{ ...e.horizons[0], baseRate: null }] } as TrackEntry;
    const evidence = screenerEvidence([partial]);
    expect(evidence.kind === 'pending' && evidence.why.state).toBe('partial');
  });
});
