import { describe, expect, it } from 'vitest';

import { DEFAULT_DECISIONS, resultsVariables } from './results';

describe('resultsVariables', () => {
  it('sends the filters in force and leaves out what is not set', () => {
    expect(
      resultsVariables('vrp', {
        filters: [
          { id: 'decision', values: ['QUALIFIED', 'WATCH'], active: true },
          { id: 'change', values: ['new'], active: false },
        ],
        q: ' dk ',
        columns: ['feature.market_cap'],
        sort: '-score',
        page: 2,
        size: 50,
      }),
    ).toEqual({
      id: 'vrp',
      filters: [
        {
          id: 'decision',
          values: ['QUALIFIED', 'WATCH'],
          min: null,
          max: null,
          within: null,
          active: true,
        },
        { id: 'change', values: ['new'], min: null, max: null, within: null, active: false },
      ],
      q: 'dk',
      columns: ['feature.market_cap'],
      sort: '-score',
      page: 2,
      size: 50,
    });
    expect(resultsVariables('vrp', { filters: [], columns: [] })).toEqual({
      id: 'vrp',
      filters: null,
      q: null,
      columns: [],
      sort: null,
    });
  });

  it('the decisions a review opens on are the picks, never the rejects', () => {
    expect(DEFAULT_DECISIONS).not.toContain('REJECT');
  });
});
