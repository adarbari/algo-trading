import { describe, expect, it } from 'vitest';

import { heldFigures, premiumLine, sizeLines, stressSentence, type MarginPreview } from './margin';

const PREVIEW = {
  contracts: 2,
  days: 28,
  cash_secured: 16000,
  margin_held: 3600,
  premium_over_cash: 0.0231,
  premium_over_margin: 0.1025,
  volume_share: 0.042,
  open_interest_share: 0.0085,
  stress: { episode: 'covid_2020', drop: -0.34, in_the_money: 1200 },
} as MarginPreview;

describe('heldFigures', () => {
  it('leads with the chosen account and shows the other as the comparison', () => {
    expect(heldFigures(PREVIEW, 'margin')).toEqual({
      headline: { label: 'Cash or margin held', value: '$3,600.00' },
      other: { label: 'Cash-secured would hold', value: '$16,000.00' },
    });
    expect(heldFigures(PREVIEW, 'cash').other).toEqual({
      label: 'Margin account would hold',
      value: '$3,600.00',
    });
  });
});

describe('premiumLine', () => {
  it('uses the premium over the chosen account and the days', () => {
    expect(premiumLine(PREVIEW, 'cash')).toBe("2.3% of what's held, for 28 days");
    expect(premiumLine(PREVIEW, 'margin')).toBe("10.3% of what's held, for 28 days");
    expect(premiumLine({ ...PREVIEW, days: 1 }, 'cash')).toContain('for 1 day');
  });
});

describe('sizeLines', () => {
  it('hides each part that is null', () => {
    expect(sizeLines(PREVIEW)).toHaveLength(2);
    expect(sizeLines({ ...PREVIEW, volume_share: null })).toEqual([
      '0.9% of the open contracts at this strike',
    ]);
    expect(sizeLines({ ...PREVIEW, volume_share: null, open_interest_share: null })).toEqual([]);
  });
});

describe('stressSentence', () => {
  it('names the worst stored episode and what it would cost', () => {
    expect(stressSentence('ORBT', PREVIEW)).toBe(
      'If ORBT fell like its worst stored episode (Covid crash, early 2020, −34%), this put would be $1,200.00 in the money on 2 contracts, before the premium. Margin multiplies losses as well as returns.',
    );
  });
  it('says nothing without a stress, and spaces an unknown episode key', () => {
    expect(stressSentence('ORBT', { ...PREVIEW, stress: null })).toBeNull();
    expect(
      stressSentence('ORBT', {
        ...PREVIEW,
        stress: { episode: 'new_one', drop: -0.1, in_the_money: 5 },
      }),
    ).toContain('(new one, −10%)');
  });
});
