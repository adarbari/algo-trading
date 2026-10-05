import { describe, expect, it } from 'vitest';

import { DEFAULT_DECISIONS, orderedDecisions, shownDecisions, tableParams } from './table';

describe('tableParams', () => {
  it('joins the lists and leaves out what is not set', () => {
    expect(
      tableParams({
        decisions: ['QUALIFIED', 'WATCH'],
        change: 'new',
        q: ' dk ',
        columns: ['feature.market_cap'],
        sort: '-score',
      }),
    ).toEqual({
      decision: 'QUALIFIED,WATCH',
      change: 'new',
      q: 'dk',
      columns: 'feature.market_cap',
      sort: '-score',
      size: 1000,
    });
    expect(tableParams({ decisions: [], columns: [] })).toEqual({
      decision: null,
      change: null,
      q: null,
      columns: null,
      sort: null,
      size: 1000,
    });
  });
});

describe('orderedDecisions', () => {
  it('lists picks first and rejects last, without empty counts', () => {
    expect(
      orderedDecisions({ REJECT: 4198, WATCH: 1, QUALIFIED: 3, EVENT_RISK: 0, ODD: 2 }),
    ).toEqual([
      { decision: 'QUALIFIED', count: 3 },
      { decision: 'WATCH', count: 1 },
      { decision: 'REJECT', count: 4198 },
      { decision: 'ODD', count: 2 },
    ]);
  });
});

describe('shownDecisions', () => {
  it('uses the saved decisions, else the picks (never the rejects)', () => {
    const view = { screener_id: 'x', saved: true, columns: [], sort: null, decisions: ['REJECT'] };
    expect(shownDecisions(view)).toEqual(['REJECT']);
    expect(shownDecisions({ ...view, saved: false, decisions: [] })).toEqual(DEFAULT_DECISIONS);
    expect(shownDecisions(undefined)).toEqual(DEFAULT_DECISIONS);
    expect(DEFAULT_DECISIONS).not.toContain('REJECT');
  });
});
