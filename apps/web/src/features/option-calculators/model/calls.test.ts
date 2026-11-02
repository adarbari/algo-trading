import { describe, expect, it } from 'vitest';

import { closedSentence, contractsText, dividendLine, type CallsPreview } from './calls';

const PREVIEW = {
  priced_at: 84.2,
  above_price: 0.031,
  contracts: 3,
} as CallsPreview;

describe('closedSentence', () => {
  it('says where the shares closed against the trader price', () => {
    expect(closedSentence('ORBT', PREVIEW)).toBe('ORBT closed at $84.20, 3.1% above your price.');
    expect(closedSentence('ORBT', { ...PREVIEW, above_price: -0.02 })).toBe(
      'ORBT closed at $84.20, 2.0% below your price.',
    );
  });
});

describe('dividendLine', () => {
  it('formats the ex-date, the amount and the own-by day', () => {
    expect(dividendLine({ ex_date: '2026-11-12', amount: 0.62, own_by: '2026-11-11' })).toEqual({
      exDate: '12 Nov 2026',
      amount: '$0.62',
      ownBy: '11 Nov 2026',
    });
  });
});

describe('contractsText', () => {
  it('counts contracts', () => {
    expect(contractsText(1)).toBe('1 contract');
    expect(contractsText(3)).toBe('3 contracts');
  });
});
