import { describe, expect, it } from 'vitest';

import { toSetupIdeas, type SetupIdeasResponse } from './setup-ideas';

const unknown = null;
const response: SetupIdeasResponse = {
  setupIdeas: {
    session: '2026-10-02',
    state: 'listed',
    ruleVersion: 1,
    total: 2,
    leftOut: [{ kind: 'no_verdict', count: 1 }],
    groups: [
      {
        edgeId: 'a',
        name: 'Setup A',
        level: 'works',
        liftPts: 2.5,
        oosTrades: 80,
        basisScreener: 'scr_a',
        basisHorizon: 20,
        state: 'picked',
        picked: 2,
        shown: 2,
        unknown,
      },
    ],
    ideas: [
      {
        rank: 1,
        instrumentId: 'EQ:X',
        setupId: 'a',
        place: 1,
        watchOut: [],
        instrument: { symbol: 'XXX', name: 'X Inc' },
        alsoIn: [{ edgeId: 'b', edgeName: 'Setup B', place: 3 }],
        metrics: [
          { name: 'hv30', value: 0.4 },
          { name: 'flag', value: true },
        ],
        result: { decision: 'QUALIFIED', regime: 'CALM', sizeMultiplier: 1 },
      },
      {
        rank: 2,
        instrumentId: 'EQ:Y',
        setupId: 'a',
        place: 2,
        watchOut: ['liquidity_risk'],
        instrument: null,
        alsoIn: [],
        metrics: [],
        result: null,
      },
    ],
  },
};

describe('toSetupIdeas', () => {
  it('is null when nothing is stored', () => {
    expect(toSetupIdeas({ setupIdeas: null })).toBeNull();
  });

  it('puts each idea under the setup the server ranked it under, in the served order', () => {
    const found = toSetupIdeas(response);
    expect(found?.state).toBe('listed');
    expect(found?.ideas.map((i) => i.rank)).toEqual([1, 2]);
    expect(found?.groups[0]?.ideas.map((i) => i.symbol)).toEqual(['XXX', null]);
    expect(found?.leftOut).toEqual([{ kind: 'no_verdict', count: 1 }]);
  });

  it('keeps only numbers and strings among the metrics, and the regime of the pick', () => {
    const first = toSetupIdeas(response)?.ideas[0];
    expect(first?.metrics).toEqual([{ name: 'hv30', value: 0.4 }]);
    expect(first?.regime).toBe('CALM');
  });

  it('reads any state but listed as unproven', () => {
    const served = response.setupIdeas;
    const found = toSetupIdeas({
      setupIdeas: served && { ...served, state: 'unproven', groups: [], ideas: [] },
    });
    expect(found?.state).toBe('unproven');
  });
});
