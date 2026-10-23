import { describe, expect, it } from 'vitest';

import type { EventStudyLinks as Study } from '../api/eventList';

import { studyEventRows } from './studyRows';

const SEC = (n: string) =>
  `https://www.sec.gov/Archives/edgar/data/1/0000000001260000${n}/0000000001-26-0000${n}-index.htm`;
const study: Study = {
  session: '2026-10-07',
  ahead: [
    {
      date: '2026-10-14',
      time: '08:30',
      kind: 'macro_release',
      label: 'CPI',
      sourceUrl: 'https://www.bls.gov/cpi/',
    },
    {
      date: '2026-10-29',
      time: 'after_hours',
      kind: 'own_earnings',
      label: 'Earnings',
      sourceUrl: null,
    },
    { date: '2026-11-20', time: 'close', kind: 'market_structure', label: 'Opex', sourceUrl: null },
  ],
  filings: [
    { filingDate: '2026-07-30', form: '8-K', label: 'Results', sourceUrl: SEC('01') },
    { filingDate: '2026-07-30', form: '8-K/A', label: 'Exhibits', sourceUrl: SEC('02') },
    { filingDate: '2026-07-01', form: '8-K', label: 'Other events', sourceUrl: null },
  ],
};

describe('studyEventRows', () => {
  it('links the macro release and each 8-K of a day, one row a day, and leaves upcoming earnings plain', () => {
    expect(studyEventRows(study, new Set())).toEqual([
      { time: '2026-07-01', kind: 'filing', parts: [{ text: '8-K Other events' }] },
      {
        time: '2026-07-30',
        kind: 'filing',
        parts: [
          { text: '8-K Results', href: SEC('01') },
          { text: '8-K/A Exhibits', href: SEC('02') },
        ],
      },
      {
        time: '2026-10-14',
        kind: 'macro',
        parts: [{ text: 'CPI 08:30', href: 'https://www.bls.gov/cpi/' }],
      },
      { time: '2026-10-29', kind: 'earnings', parts: [{ text: 'Earnings, after the close' }] },
    ]);
  });

  it('leaves an earnings date the stored events already show to them', () => {
    const rows = studyEventRows(study, new Set(['2026-10-29']));
    expect(rows.some((r) => r.kind === 'earnings')).toBe(false);
  });
});
