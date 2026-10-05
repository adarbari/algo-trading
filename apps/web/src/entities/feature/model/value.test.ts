import { describe, expect, it } from 'vitest';

import {
  codeReason,
  isUnknown,
  shownValue,
  unknownLabel,
  unknownReason,
  valueFormat,
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
    code: 'NO_PARTITION' | 'NO_ROW' | 'NULL' | 'LICENCE' | 'NOT_APPLICABLE' | 'ILLIQUID',
  ): ServedValue => ({
    name: 'rollup.earnings@v1.next_earnings_date',
    value: null,
    unknown: { code, detail: 'rollups/instrument/earnings@v1 has no partition for 2026-10-02' },
    info: { format: 'DATE', nullMeaning: 'no report date on or after the session' },
  });

  it('says why, in words', () => {
    expect(unknownReason(value('NO_PARTITION'))).toBe(
      'not stored for this session (rollups/instrument/earnings@v1 has no partition for 2026-10-02)',
    );
    expect(unknownReason(value('NO_ROW'))).toBe('no row for this instrument in this session');
    expect(unknownReason(value('NULL'))).toBe('no report date on or after the session');
    expect(unknownReason(value('LICENCE'))).toMatch(/has no partition/);
    expect(unknownReason(undefined)).toBe('not known');
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
    expect(unknownReason(value('ILLIQUID'))).toMatch(/has no partition/); // the server's detail
  });
});
