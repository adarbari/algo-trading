import { describe, expect, it } from 'vitest';

import type { EventRow } from '../api/eventList';

import { storedEventRows } from './storedRows';

const SEC =
  'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/0000000001-26-000001-index.htm';
const row = (
  kind: string,
  date: string,
  values: object,
  extra: Partial<EventRow> = {},
): EventRow => ({
  table: `events/${kind}`,
  kind,
  date,
  ts: `${date}T00:00:00+00:00`,
  values,
  sourceUrl: null,
  confirmed: false,
  ...extra,
});

describe('storedEventRows', () => {
  it('describes dividends, splits and earnings, oldest first, linking nothing without a page', () => {
    const rows = storedEventRows([
      row('dividend', '2026-08-10', { cash_amount: 0.27 }),
      row('split', '2024-06-10', { split_from: 1, split_to: 10 }),
      row('reference_change', '2026-10-02', { change: 'added', new: 'X' }),
      row('earnings', '2026-10-29', { fiscal_quarter: 'Sep/2026', time: 'post', reported: false }),
    ]);
    expect(rows.map((r) => [r.time, r.kind, r.parts?.[0]?.text])).toEqual([
      ['2024-06-10', 'split', 'Split 10-for-1'],
      ['2026-08-10', 'dividend', 'Ex-dividend $0.27 cash'],
      ['2026-10-29', 'earnings', 'Earnings, Quarter Sep/2026 · after the close · not reported yet'],
    ]);
    expect(rows.every((r) => r.parts?.[0]?.href === undefined)).toBe(true);
  });

  it("keeps the server's confirmed 8-K row of a day, with its page", () => {
    const calendar = row('earnings', '2026-10-29', { time: 'post', reported: false });
    const eightK = row(
      'earnings',
      '2026-10-29',
      { time: 'intraday', reported: true, eps_reported: 2.1 },
      { confirmed: true, sourceUrl: SEC },
    );
    for (const events of [
      [calendar, eightK],
      [eightK, calendar],
    ]) {
      const rows = storedEventRows(events);
      expect(rows).toHaveLength(1);
      expect(rows[0]?.parts).toEqual([{ text: 'Earnings, reported $2.10', href: SEC }]);
    }
  });

  it('reads reported with no link when the confirmed 8-K matched no filing', () => {
    const eightK = row(
      'earnings',
      '2026-10-29',
      { reported: true, eps_reported: 2.1 },
      { confirmed: true },
    );
    const rows = storedEventRows([row('earnings', '2026-10-29', { reported: false }), eightK]);
    expect(rows[0]?.parts).toEqual([{ text: 'Earnings, reported $2.10' }]);
  });
});
