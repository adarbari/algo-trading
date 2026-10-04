import { describe, expect, it } from 'vitest';

import { addDays, addMonths, daysBetween, todayIso } from './calendar-days';

describe('calendar days', () => {
  it('moves by months and days in UTC', () => {
    expect(addMonths('2026-10-02', -12)).toBe('2025-10-02');
    expect(addMonths('2026-10-02', -3)).toBe('2026-07-02');
    expect(addDays('2026-10-02', -90)).toBe('2026-07-04');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
  });

  it('counts days between two dates', () => {
    expect(daysBetween('2026-10-02', '2026-11-20')).toBe(49);
    expect(daysBetween('2026-10-02', '2026-10-02')).toBe(0);
    expect(daysBetween('2026-10-05', '2026-10-02')).toBe(-3);
  });

  it("gives today's UTC day", () => {
    expect(todayIso(new Date('2026-10-03T23:30:00Z'))).toBe('2026-10-03');
  });
});
