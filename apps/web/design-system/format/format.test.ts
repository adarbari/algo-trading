import { describe, expect, it } from 'vitest';

import { formatValue, isNumericFormat, MISSING } from './format';

const text = (value: unknown, format: Parameters<typeof formatValue>[1]) =>
  formatValue(value, format).text;

describe('formatValue', () => {
  it('shows missing values as an em dash with a muted tone', () => {
    for (const value of [null, undefined, '', Number.NaN]) {
      expect(formatValue(value, { kind: 'number' })).toEqual({ text: MISSING, tone: 'muted' });
    }
  });

  it('groups numbers and uses a typographic minus', () => {
    expect(text(11427, { kind: 'number' })).toBe('11,427');
    expect(text(1.4912, { kind: 'number', digits: 2 })).toBe('1.49');
    expect(text(-3.1, { kind: 'number', digits: 1 })).toBe('−3.1');
  });

  it('shows a fraction as a percent', () => {
    expect(text(0.721, { kind: 'percent' })).toBe('72.1%');
    expect(text(0.0032, { kind: 'percent', digits: 2 })).toBe('0.32%');
  });

  it('formats dollars, plain and compact', () => {
    expect(text(333.69, { kind: 'currency' })).toBe('$333.69');
    expect(text(13_990_000_000, { kind: 'currency-compact' })).toBe('$13.99B');
    expect(text(412_350_000, { kind: 'currency-compact' })).toBe('$412M');
    expect(text(1_594_000_000, { kind: 'currency-compact' })).toBe('$1.59B');
    expect(text(96_200_000, { kind: 'currency-compact' })).toBe('$96.2M');
    expect(text(4_870_000_000_000, { kind: 'currency-compact' })).toBe('$4.87T');
    expect(text(-1_200_000_000, { kind: 'currency-compact' })).toBe('−$1.2B');
    expect(text(11427, { kind: 'compact' })).toBe('11.4K');
  });

  it('formats calendar dates without a time-zone shift', () => {
    expect(text('2026-10-02', { kind: 'date' })).toBe('2 Oct 2026');
    expect(text('2026-10-02', { kind: 'date', style: 'weekday' })).toBe('Fri 2 Oct');
    expect(text('2026-10-02', { kind: 'date', style: 'iso' })).toBe('2026-10-02');
    expect(text('not a date', { kind: 'date' })).toBe(MISSING);
  });

  it('signs deltas and gives them an up / down tone', () => {
    expect(formatValue(0.0124, { kind: 'delta' })).toEqual({ text: '+1.24%', tone: 'up' });
    expect(formatValue(-0.0087, { kind: 'delta' })).toEqual({ text: '−0.87%', tone: 'down' });
    expect(formatValue(3.2, { kind: 'delta', unit: 'points' })).toEqual({
      text: '+3.2 pts',
      tone: 'up',
    });
    expect(formatValue(0.00001, { kind: 'delta' })).toEqual({ text: '0.00%', tone: 'default' });
  });

  it('shows non-numbers given a numeric format as text', () => {
    expect(text('n/a', { kind: 'number' })).toBe('n/a');
  });

  it('knows which formats are numeric', () => {
    expect(isNumericFormat({ kind: 'percent' })).toBe(true);
    expect(isNumericFormat({ kind: 'date' })).toBe(false);
    expect(isNumericFormat(undefined)).toBe(false);
  });
});
