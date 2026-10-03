import { describe, expect, it } from 'vitest';

import { formatNumber, formatPercent, formatSignedPercent, MISSING } from './number';

describe('number formatting', () => {
  it('formats fixed decimals with grouping', () => {
    expect(formatNumber(1234.5)).toBe('1,234.50');
    expect(formatNumber(3, 0)).toBe('3');
  });

  it('formats ratios as percentages', () => {
    expect(formatPercent(0.1234)).toBe('12.34%');
    expect(formatSignedPercent(0.0124)).toBe('+1.24%');
    expect(formatSignedPercent(-0.0087)).toBe('-0.87%');
    expect(formatSignedPercent(0)).toBe('0.00%');
  });

  it('shows missing values as a dash', () => {
    expect(formatNumber(null)).toBe(MISSING);
    expect(formatPercent(undefined)).toBe(MISSING);
    expect(formatSignedPercent(Number.NaN)).toBe(MISSING);
  });
});
