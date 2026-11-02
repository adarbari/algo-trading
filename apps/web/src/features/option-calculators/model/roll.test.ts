import { describe, expect, it } from 'vitest';

import { rollSentence, shownRolls, VISIBLE_ROLLS, type RollPreview, type RollRow } from './roll';

const PREVIEW: RollPreview = {
  underlying_id: 'EQ:X',
  session: '2026-10-23',
  priced_at: 79.3,
  right: 'put',
  strike: 80,
  expiry: '2026-10-30',
  sold_at: 1.4,
  buy_back: 1.85,
  over_collected: 0.45,
  above_strike: -0.009,
  days_left: 7,
  delta: -0.4,
  rolls: [],
};

describe('rollSentence', () => {
  it('says what buying back costs against what was collected, and where the shares stand', () => {
    expect(rollSentence('ORBT', PREVIEW)).toBe(
      'Buying it back now costs $1.85 (middle price): $0.45 a share more than you collected. ORBT is 0.9% below your strike, with 7 days left.',
    );
  });

  it('says less than collected when the server sent a negative figure, above when the shares are over the strike', () => {
    const text = rollSentence('ORBT', {
      ...PREVIEW,
      over_collected: -0.3,
      above_strike: 0.05,
      days_left: 1,
    });
    expect(text).toContain('$0.30 a share less than you collected');
    expect(text).toContain('5.0% above your strike, with 1 day left.');
  });

  it('leaves the comparison out without a sold-at price', () => {
    expect(rollSentence('ORBT', { ...PREVIEW, sold_at: null, over_collected: null })).toMatch(
      /^Buying it back now costs \$1\.85 \(middle price\)\. ORBT is/,
    );
  });
});

describe('shownRolls', () => {
  const rolls = Array.from({ length: 6 }, (_, i) => ({ strike: 80 - i }) as RollRow);
  it('shows the first few until all are asked for', () => {
    expect(shownRolls(rolls, false)).toHaveLength(VISIBLE_ROLLS);
    expect(shownRolls(rolls, true)).toHaveLength(6);
  });
});
