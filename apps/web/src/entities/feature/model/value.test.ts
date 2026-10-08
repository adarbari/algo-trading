import { describe, expect, it } from 'vitest';

import {
  codeReason,
  isUnknown,
  reasonLabel,
  shownValue,
  unknownLabel,
  valueFormat,
  type NullReasonName,
  type ServedValue,
} from './value';

describe('valueFormat', () => {
  it('follows the server format, the unit choosing currency and digits', () => {
    expect(valueFormat({ format: 'PERCENT' })).toEqual({ kind: 'percent' });
    expect(valueFormat({ format: 'CURRENCY' })).toEqual({ kind: 'currency' });
    expect(valueFormat({ format: 'COMPACT', unit: 'usd' })).toEqual({ kind: 'currency-compact' });
    expect(valueFormat({ format: 'COMPACT', unit: 'shares' })).toEqual({ kind: 'compact' });
    expect(valueFormat({ format: 'NUMBER', unit: 'ratio' })).toEqual({ kind: 'number', digits: 2 });
    expect(valueFormat({ format: 'NUMBER', unit: 'pct_points' })).toEqual({
      kind: 'number',
      digits: 1,
    });
    expect(valueFormat({ format: 'NUMBER', dtype: 'float32' })).toEqual({
      kind: 'number',
      digits: 2,
    });
    expect(valueFormat({ format: 'NUMBER', unit: 'sessions', dtype: 'int' })).toEqual({
      kind: 'number',
      digits: 0,
    });
    expect(valueFormat({ format: 'DATE' })).toEqual({ kind: 'date' });
    for (const format of ['FLAG', 'CATEGORY', 'TEXT'] as const) {
      expect(valueFormat({ format })).toEqual({ kind: 'text' });
    }
  });
});

describe('unknown values', () => {
  const value = (
    code: 'NO_PARTITION' | 'NO_ROW' | 'NULL' | 'LICENCE' | 'NOT_APPLICABLE',
  ): ServedValue => ({
    name: 'rollup.earnings@v1.next_earnings_date',
    value: null,
    unknown: { code, kind: 'SYSTEM', guideTerm: 'unavailable_system', cause: null },
    info: { format: 'DATE', nullMeaning: 'no report date on or after the session' },
  });

  it('tells a known value from an unknown one and shows flags in words', () => {
    expect(isUnknown(value('NULL'))).toBe(true);
    expect(isUnknown(undefined)).toBe(true);
    expect(isUnknown({ ...value('NULL'), value: 0, unknown: null })).toBe(false);
    expect([shownValue(true), shownValue(false), shownValue(3)]).toEqual(['Yes', 'No', 3]);
  });

  it('labels n/a and Illiquid cells apart from a real gap, with a reason for each', () => {
    expect(unknownLabel('NOT_APPLICABLE')).toBe('n/a');
    expect(unknownLabel('ILLIQUID')).toBe('Illiquid');
    expect([unknownLabel('NULL'), unknownLabel('NO_ROW'), unknownLabel(null)]).toEqual([
      'Unknown',
      'Unknown',
      'Unknown',
    ]);
    expect(codeReason('NOT_APPLICABLE', null)).toMatch(/does not apply/);
    expect(codeReason('ILLIQUID', null)).toMatch(/too thin to price/);
  });

  it('words each explained absence, exhaustively (ADR 0046)', () => {
    const reasons: NullReasonName[] = ['NO_TRADE', 'NOT_ANNOUNCED', 'NEW_LISTING', 'FEW_BARS'];
    expect(reasons.map(reasonLabel)).toEqual([
      'No trade',
      'Not announced',
      'New listing',
      'Too few trades',
    ]);
    expect(reasons.map((r) => unknownLabel('EXPLAINED', r))).toEqual(reasons.map(reasonLabel));
    expect(codeReason('EXPLAINED', null, 'NO_TRADE')).toBe('no trade on this session: no bar');
    expect(codeReason('EXPLAINED', null, 'NOT_ANNOUNCED')).toBe(
      'the next report date is not announced',
    );
    expect(codeReason('EXPLAINED', null, 'NEW_LISTING')).toBe('listed too recently for the window');
    expect(codeReason('EXPLAINED', null, 'FEW_BARS')).toBe('trades too rarely to fill the window');
  });

  it('reads an EXPLAINED cell without a reason as Unknown, ', () => {
    expect(unknownLabel('EXPLAINED')).toBe('Unknown');
    expect(unknownLabel('EXPLAINED', null)).toBe('Unknown');
    expect(codeReason('EXPLAINED', null)).toBe('not known for this session');
  });
});
