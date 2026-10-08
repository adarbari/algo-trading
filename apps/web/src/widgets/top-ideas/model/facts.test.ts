import { describe, expect, it } from 'vitest';

import { IDEA_FACTS, type Idea, type IdeaPick } from '@/entities/idea';
import type { ServedValue } from '@/entities/feature';

import {
  dteReason,
  earningsCell,
  expiryDte,
  iv30,
  sessionsToEarnings,
  UNKNOWN_LABEL,
} from './facts';

const known = (name: string, value: unknown): ServedValue => ({
  name,
  value,
  unknown: null,
  info: { format: 'DATE' },
});
const unknown = (name: string, code: 'NULL' | 'NO_PARTITION'): ServedValue => ({
  name,
  value: null,
  unknown: {
    code,
    kind: code === 'NO_PARTITION' ? 'SYSTEM' : 'NOT_STORED',
    guideTerm: code === 'NO_PARTITION' ? 'unavailable_system' : 'unavailable_not_stored',
    cause: null,
  },
  info: { format: 'DATE', nullMeaning: 'no report date on or after the session' },
});

const pick: IdeaPick = {
  screenerId: 's',
  screenerName: 'S',
  flags: [],
  columns: {},
  criterionValues: {},
  decision: 'QUALIFIED',
  score: 1,
  reasons: '',
};
const idea = (facts: ServedValue[]): Idea => ({
  instrumentId: 'id',
  symbol: 'X',
  rank: 1,
  picks: [pick],
  best: pick,
  regime: null,
  sizeMultiplier: null,
  facts: Object.fromEntries(facts.map((f) => [f.name, f])),
  metrics: {},
  watchOut: [],
});

describe('earningsCell', () => {
  it('shows the next report date', () => {
    const axti = idea([known(IDEA_FACTS.nextEarnings, '2026-11-05')]);
    expect(earningsCell(axti)).toEqual({ text: 'Thu 5 Nov', muted: false });
  });

  it('falls back to a muted "Last <d MMM>" when no next date is stored (MRVL)', () => {
    const mrvl = idea([
      unknown(IDEA_FACTS.nextEarnings, 'NULL'),
      known(IDEA_FACTS.lastEarnings, '2026-08-27'),
    ]);
    expect(earningsCell(mrvl)).toEqual({
      text: 'Last 27 Aug',
      muted: true,
      title: 'no report date on or after the session',
    });
  });

  it('says UNKNOWN, and why, when neither date is known', () => {
    const none = idea([
      unknown(IDEA_FACTS.nextEarnings, 'NO_PARTITION'),
      unknown(IDEA_FACTS.lastEarnings, 'NO_PARTITION'),
    ]);
    expect(earningsCell(none)).toEqual({
      text: UNKNOWN_LABEL,
      muted: true,
      title: 'not available because of a system error',
    });
    expect(earningsCell(idea([]))).toEqual({
      text: UNKNOWN_LABEL,
      muted: true,
      title: 'not known',
    });
  });
});

describe('the other served facts', () => {
  it('reads numbers as served and says why one is missing', () => {
    const x = idea([
      known(IDEA_FACTS.sessionsToEarnings, 9),
      known(IDEA_FACTS.iv30, 0.42),
      unknown(IDEA_FACTS.expiryDte, 'NO_PARTITION'),
    ]);
    expect([sessionsToEarnings(x), iv30(x), expiryDte(x)]).toEqual([9, 0.42, null]);
    expect(dteReason(x)).toBe('not available because of a system error');
    expect(dteReason(idea([known(IDEA_FACTS.expiryDte, 3)]))).toBeUndefined();
  });
});
