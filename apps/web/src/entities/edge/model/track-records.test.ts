import { describe, expect, it } from 'vitest';

import { TRACK_RECORDS_FIXTURE } from './fixtures';
import { oddsEntry, recordFigures, toTrackRecords } from './track-records';

const records = toTrackRecords(TRACK_RECORDS_FIXTURE);
const of = (id: string) => records.get(id) ?? [];

describe('oddsEntry', () => {
  it('is the first record that ran, none when no edge ran', () => {
    expect(oddsEntry(of('momentum_12_1'))?.edgeId).toBe('momentum_12_1');
    expect(oddsEntry(of('vrp_scanner'))).toBeNull();
  });
});

describe('recordFigures', () => {
  it('reads the first horizon of the first record that ran', () => {
    expect(recordFigures(of('momentum_12_1'))).toMatchObject({
      edgeId: 'momentum_12_1',
      hitRate: 0.58,
      baseRate: 0.51,
      sessions: 120,
    });
  });

  it('is null when no edge ran or lists it', () => {
    expect(recordFigures(of('vrp_scanner'))).toBeNull();
    expect(recordFigures(of('plain'))).toBeNull();
  });
});
