import { describe, expect, it } from 'vitest';

import { afterLatest, dateError } from './date';

describe('dateError', () => {
  it('accepts a real calendar date and refuses other text', () => {
    expect(dateError('2026-04-01')).toBeNull();
    expect(dateError('2024-02-29')).toBeNull();
    expect(dateError('2026-02-30')).toBe('That is not a calendar date.');
    expect(dateError('04/01/2026')).toBe('Use the form 2026-04-01.');
  });
});

describe('afterLatest', () => {
  it('names the latest stored session when the date is past it', () => {
    expect(afterLatest('2026-10-01', '2026-09-30')).toBe('No stored session after 2026-09-30.');
    expect(afterLatest('2026-09-30', '2026-09-30')).toBeNull();
  });
});
