import { describe, expect, it } from 'vitest';

import { isIsoDate } from './date';

describe('isIsoDate', () => {
  it('accepts a real day written yyyy-mm-dd', () => {
    expect(isIsoDate('2026-04-01')).toBe(true);
    expect(isIsoDate('2028-02-29')).toBe(true);
  });

  it('refuses text, other formats and days that do not exist', () => {
    for (const bad of [
      '',
      'April 1',
      '2026-4-1',
      '01/04/2026',
      '2026-02-30',
      '2027-02-29',
      '2026-13-01',
    ]) {
      expect(isIsoDate(bad), bad).toBe(false);
    }
  });
});
