import { describe, expect, it } from 'vitest';

import { isUnknown, shownValue, valueFormat, type ServedValue } from './value';

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
    unknown: {
      code,
      kind: 'SYSTEM',
      guideTerm: 'unavailable_system',
      kindText: 'not available because of a system error',
      cause: null,
    },
    info: { format: 'DATE', nullMeaning: 'no report date on or after the session' },
  });

  it('tells a known value from an unknown one and shows flags in words', () => {
    expect(isUnknown(value('NULL'))).toBe(true);
    expect(isUnknown(undefined)).toBe(true);
    expect(isUnknown({ ...value('NULL'), value: 0, unknown: null })).toBe(false);
    expect([shownValue(true), shownValue(false), shownValue(3)]).toEqual(['Yes', 'No', 3]);
  });
});
