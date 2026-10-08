import { describe, expect, it } from 'vitest';

import { resultRows, type ResultsPage } from './rows';

describe('resultRows', () => {
  it('carries the reason of an explained absence into the cell', () => {
    const page = {
      columns: [{ name: 'feature.pct_from_high_avail' }],
      rows: [[null]],
      unknown: [['EXPLAINED']],
      reasons: [['NEW_LISTING']],
      kinds: [['NOT_APPLICABLE']],
      kindTexts: [{ kind: 'NOT_APPLICABLE', text: 'does not apply to this instrument' }],
      results: [
        {
          instrumentId: 'EQ:N',
          instrument: { symbol: 'NEW', name: 'New Co' },
          rank: 1,
          decision: 'QUALIFIED',
          score: 90,
          flags: [],
          criteria: [],
          columns: [],
          reasons: '',
        },
      ],
    } as unknown as ResultsPage;
    expect(resultRows(page)[0]?.cells['feature.pct_from_high_avail']).toEqual({
      value: null,
      unknown: 'EXPLAINED',
      reason: 'NEW_LISTING',
      kind: 'NOT_APPLICABLE',
      kindText: 'does not apply to this instrument',
    });
  });
});
