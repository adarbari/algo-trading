import { describe, expect, it } from 'vitest';

import type { RecentRun } from '@/entities/screen';
import { runLineParts, stripItems } from './recent-runs';

const RAN: RecentRun = {
  session: '2026-10-22',
  state: 'PARTIAL',
  served: true,
  runId: 'r1',
  configVersion: 3,
  picked: 12,
  newPicks: 2,
  dropped: 1,
  leftOutShare: 0.08,
  notRun: null,
};
const GAP: RecentRun = {
  ...RAN,
  session: '2026-10-21',
  state: 'NOT_RUN',
  served: false,
  runId: null,
  configVersion: null,
  picked: null,
  newPicks: null,
  dropped: null,
  leftOutShare: null,
};

describe('stripItems', () => {
  it('labels each session with its day and state, tones it and marks the served one', () => {
    expect(stripItems([GAP, RAN])).toEqual([
      { label: 'Oct 21: Not run', tone: 'muted', current: false },
      { label: 'Oct 22: Partial, 12 picked', tone: 'warning', current: true },
    ]);
  });
});

describe('runLineParts', () => {
  it('words the counts the server sent', () => {
    expect(runLineParts(RAN)).toEqual({
      session: '2026-10-22',
      state: 'PARTIAL',
      version: 'v3',
      picked: '12 picked',
      changes: '+2 new, −1 dropped',
      leftOut: 'Missing data for 8% of names',
    });
  });

  it('leaves out a count that was not stored, never says 0', () => {
    const parts = runLineParts({ ...RAN, newPicks: null, dropped: null, leftOutShare: null });
    expect(parts.changes).toBeNull();
    expect(parts.leftOut).toBeNull();
  });
});
