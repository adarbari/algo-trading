import { describe, expect, it } from 'vitest';

import { DEFAULT_DECISIONS, orderedDecisions, resultsVariables, shownDecisions } from './results';

describe('resultsVariables', () => {
  it('keeps the lists and leaves out what is not set', () => {
    expect(
      resultsVariables('vrp', {
        decisions: ['QUALIFIED', 'WATCH'],
        change: 'new',
        q: ' dk ',
        columns: ['feature.market_cap'],
        sort: '-score',
        page: 2,
        size: 50,
      }),
    ).toEqual({
      id: 'vrp',
      decisions: ['QUALIFIED', 'WATCH'],
      change: 'new',
      q: 'dk',
      columns: ['feature.market_cap'],
      sort: '-score',
      page: 2,
      size: 50,
    });
    expect(resultsVariables('vrp', { decisions: [], columns: [] })).toEqual({
      id: 'vrp',
      decisions: null,
      change: null,
      q: null,
      columns: [],
      sort: null,
    });
  });
});

describe('orderedDecisions', () => {
  it('lists picks first and rejects last, without empty counts', () => {
    const counts = [
      { decision: 'REJECT', count: 4198 },
      { decision: 'WATCH', count: 1 },
      { decision: 'QUALIFIED', count: 3 },
      { decision: 'EVENT_RISK', count: 0 },
      { decision: 'ODD', count: 2 },
    ];
    expect(orderedDecisions(counts)).toEqual([
      { decision: 'QUALIFIED', count: 3 },
      { decision: 'WATCH', count: 1 },
      { decision: 'REJECT', count: 4198 },
      { decision: 'ODD', count: 2 },
    ]);
  });
});

describe('shownDecisions', () => {
  it('uses the saved decisions, else the picks (never the rejects)', () => {
    expect(shownDecisions({ saved: true, decisions: ['REJECT'] })).toEqual(['REJECT']);
    expect(shownDecisions({ saved: false, decisions: [] })).toEqual(DEFAULT_DECISIONS);
    expect(shownDecisions(undefined)).toEqual(DEFAULT_DECISIONS);
    expect(DEFAULT_DECISIONS).not.toContain('REJECT');
  });
});
