import { describe, expect, it } from 'vitest';

import { regimeFixture } from './fixtures';
import type { RegimeEpisode } from './regime';
import {
  detailRows,
  overviewRow,
  signalName,
  signalNote,
  type EpisodeSignals,
  type SignalTiming,
} from './signals';

const timing = (overrides: Partial<SignalTiming>): SignalTiming => ({
  indicator: 'curve_10y3m',
  kind: 'SLOW',
  state: 'LED',
  flaggedDay: -40,
  clearedDay: 25,
  flaggedDayFromTrough: null,
  firstKnownDay: null,
  neverFired: false,
  unknownReason: null,
  ...overrides,
});

const GATE = timing({ indicator: 'gate', kind: 'GATE', flaggedDay: 8, clearedDay: null });
const SIGNALS: EpisodeSignals = {
  gate: GATE,
  indicators: [
    timing({}),
    timing({ indicator: 'sahm', state: 'LATE', flaggedDay: 90, clearedDay: null }),
    timing({
      indicator: 'hy_oas',
      state: 'NEVER_FIRED',
      flaggedDay: null,
      clearedDay: null,
      neverFired: true,
    }),
    timing({
      indicator: 'nfci',
      state: 'UNKNOWN',
      flaggedDay: null,
      clearedDay: null,
      unknownReason: {
        code: 'NO_ROW',
        kind: 'NOT_STORED',
        guideTerm: 'unavailable_not_stored',
        kindText: 'not stored for this session',
        cause: null,
      },
    }),
    timing({ indicator: 'vix_term', kind: 'FAST', firstKnownDay: -10, flaggedDay: -10 }),
  ],
};
const EPISODE = { key: 'gfc_2008', name: 'Financial crisis, 2007-09' } as RegimeEpisode;
const INDICATORS = regimeFixture().indicators;

describe('signalNote', () => {
  it('words the server state, never from the days', () => {
    expect(SIGNALS.indicators.slice(0, 4).map((timing) => signalNote(timing))).toEqual([
      undefined,
      'Late',
      'Never fired',
      expect.stringMatching(/^Unknown: /) as unknown,
    ]);
  });
});

describe('signalName', () => {
  it('names the gate, a known card by its plain name and an unknown key spaced', () => {
    expect(signalName(GATE, INDICATORS)).toBe('Screener gate');
    expect(signalName(timing({ indicator: 'some_card' }), [])).toBe('some card');
    const [first] = INDICATORS;
    expect(signalName(timing({ indicator: first?.key ?? '' }), INDICATORS)).toBe(first?.plainName);
  });
});

describe('overviewRow', () => {
  it('puts a marker where each signal flagged, the gate a diamond, a late one hollow', () => {
    const row = overviewRow(EPISODE, SIGNALS, INDICATORS);
    expect(row.label).toBe('Financial crisis, 2007-09');
    expect(row.markers?.map((m) => [m.id, m.at])).toEqual([
      ['gate', 8],
      ['curve_10y3m', -40],
      ['sahm', 90],
      ['vix_term', -10],
    ]);
    expect(row.markers?.[0]).toMatchObject({ shape: 'diamond', tone: 'neutral' });
    expect(row.markers?.[2]).toMatchObject({ hollow: true, tone: 's2' });
    expect(row.markers?.[3]).toMatchObject({ tone: 's1' });
  });

  it('has no markers when the session stores no signals', () => {
    expect(overviewRow(EPISODE, null, INDICATORS).markers).toEqual([]);
  });
});

describe('detailRows', () => {
  it('draws a bar from flagged to cleared, open while on, the gate first', () => {
    const rows = detailRows(SIGNALS, INDICATORS);
    expect(rows.map((r) => r.id)).toEqual([
      'gate',
      'curve_10y3m',
      'sahm',
      'hy_oas',
      'nfci',
      'vix_term',
    ]);
    expect(rows[1]?.spans?.[0]).toMatchObject({ from: -40, to: 25 });
    expect(rows[0]?.spans?.[0]).toMatchObject({ from: 8, to: null });
    expect(rows[0]?.markers).toHaveLength(1);
    expect(rows[2]).toMatchObject({ note: 'Late' });
    expect(rows[2]?.spans?.[0]).toMatchObject({ variant: 'outline' });
    expect(rows[3]).toMatchObject({ note: 'Never fired', spans: [] });
    expect(rows[4]?.note).toMatch(/^Unknown: /);
    expect(rows[5]?.spans?.[0]).toMatchObject({ openStart: true });
  });
});
