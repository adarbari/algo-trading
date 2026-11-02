import { describe, expect, it } from 'vitest';

import { toIdeaDetail, type IdeaDetailResponse } from './idea-detail';

const setup = {
  edgeId: 'a',
  edgeName: 'Setup A',
  tab: 'PREMIUM',
  level: 'works',
  place: 2,
} as const;
const idea = {
  session: '2026-10-02',
  instrumentId: 'EQ:X',
  tab: 'STOCKS',
  instrument: { symbol: 'XXX', name: 'X Inc' },
  setup: { ...setup, tab: 'STOCKS' },
  setups: [{ ...setup, tab: 'STOCKS' }, setup],
  why: {
    thesis: 't',
    mechanism: 'm',
    basisScreener: 'scr',
    decision: null,
    criteria: [],
    unknown: null,
  },
  exitRule: {
    edgeId: 'a',
    holdSessions: null,
    winners: 0,
    inSampleOnly: false,
    stop: null,
    unknown: null,
  },
  evidence: {
    level: 'works',
    result: 'r',
    basis: null,
    basisHorizon: null,
    liftPts: null,
    lift: null,
    trades: null,
    oosTrades: null,
  },
  risks: { persistence: 'p', holdEnds: null, watchOut: [], events: [], unknown: null },
  learn: 'a',
} as unknown as NonNullable<IdeaDetailResponse['idea']>;

describe('toIdeaDetail', () => {
  it('is null when no setup picked the name', () => {
    expect(toIdeaDetail({ idea: null })).toBeNull();
  });

  it('keeps the served sections and reads the tab of each setup', () => {
    const found = toIdeaDetail({ idea });
    expect(found?.symbol).toBe('XXX');
    expect(found?.setups.map((s) => s.tab)).toEqual(['stocks', 'premium']);
    expect(found?.learn).toBe('a');
    expect(found?.why.basisScreener).toBe('scr');
  });
});
