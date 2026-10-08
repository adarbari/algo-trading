import { describe, expect, it } from 'vitest';

import { CALENDAR_FIXTURE, STUDY_FIXTURE } from './fixtures';
import {
  aheadItems,
  calendarDays,
  eventItem,
  filingItem,
  gapLines,
  ladderRows,
  MARKET_NAME,
  studyChartEvents,
} from './items';

const AHEAD0 = STUDY_FIXTURE.ahead[0] as (typeof STUDY_FIXTURE.ahead)[number];
const FILING0 = STUDY_FIXTURE.filings[0] as (typeof STUDY_FIXTURE.filings)[number];
const DAY1 = CALENDAR_FIXTURE.days[1] as (typeof CALENDAR_FIXTURE.days)[number];

describe('eventItem', () => {
  it('keeps the API text and reads a missing known-from as the session', () => {
    expect(eventItem(AHEAD0, '2026-10-07')).toEqual({
      date: '2026-10-14',
      time: '08:30',
      kind: 'macro_release',
      label: 'CPI',
      source: 'BLS',
      knownFrom: '2026-10-07',
    });
  });

  it('drops a kind with no chip', () => {
    expect(eventItem({ ...AHEAD0, kind: 'novel' }, '2026-10-07')).toBeNull();
    expect(aheadItems(STUDY_FIXTURE)).toHaveLength(3);
  });
});

describe('filingItem', () => {
  it('is a filing chip with the API label and the acceptance time', () => {
    expect(filingItem(FILING0)).toMatchObject({
      kind: 'filing',
      date: '2026-07-30',
      time: '20:31 UTC',
      label: 'Results',
      knownFrom: '2026-07-30',
    });
  });
});

describe('ladderRows', () => {
  it('passes clear and marks the rung the API marked', () => {
    expect(ladderRows(STUDY_FIXTURE).map((r) => [r.expiry, r.dte, r.clear, r.firstClear])).toEqual([
      ['2026-10-16', 9, false, false],
      ['2026-10-23', 16, true, true],
    ]);
    expect(ladderRows(STUDY_FIXTURE)[0]?.events.map((e) => e.label)).toEqual(['CPI']);
  });
});

describe('gapLines', () => {
  it('says the part and why, by kind', () => {
    expect(
      gapLines([
        {
          instrumentId: null,
          part: 'macro_release',
          unknown: {
            code: 'NO_PARTITION',
            kind: 'SYSTEM',
            guideTerm: 'unavailable_system',
            reason: null,
            cause: null,
          },
        },
        {
          instrumentId: null,
          part: 'filings',
          unknown: {
            code: 'NOT_APPLICABLE',
            kind: 'NOT_APPLICABLE',
            guideTerm: 'unavailable_not_applicable',
            reason: null,
            cause: null,
          },
        },
      ]),
    ).toEqual([
      'Macro releases: not available because of a system error',
      'Filings: does not apply to this instrument',
    ]);
  });

  it('reads two identical gaps once, so a list keyed by the line has unique keys', () => {
    const gap: Parameters<typeof gapLines>[0][number] = {
      instrumentId: null,
      part: 'fund_reference',
      unknown: {
        code: 'NO_PARTITION',
        kind: 'SYSTEM',
        guideTerm: 'unavailable_system',
        reason: null,
        cause: null,
      },
    };
    const lines = gapLines([gap, { ...gap }]);
    expect(lines).toHaveLength(1);
    expect(new Set(lines).size).toBe(lines.length);
  });
});

describe('studyChartEvents', () => {
  it('marks filings, macro dates and own earnings the stored events do not already mark', () => {
    expect(studyChartEvents(STUDY_FIXTURE, new Set())).toEqual([
      { time: '2026-07-30', kind: 'filing', detail: '8-K Results' },
      { time: '2026-10-14', kind: 'macro', detail: 'CPI 08:30' },
      { time: '2026-10-29', kind: 'earnings', detail: 'after the close' },
    ]);
    expect(
      studyChartEvents(STUDY_FIXTURE, new Set(['2026-10-29'])).some((e) => e.kind === 'earnings'),
    ).toBe(false);
  });
});

describe('calendarDays', () => {
  it('puts market-wide events in a Market column and rules the expiry days', () => {
    const { days, names, ruledDays } = calendarDays(CALENDAR_FIXTURE);
    expect(names.map((n) => n.symbol)).toEqual(['Market', 'AAPL', 'NVDA']);
    expect(days[0]?.events[0]).toMatchObject({ instrumentId: MARKET_NAME.id, symbol: 'Market' });
    expect(days[1]?.events[0]).toMatchObject({ instrumentId: 'FIGI-AAPL', symbol: 'AAPL' });
    expect(ruledDays).toEqual(['2026-11-20']);
  });

  it('rules only the days the API flags as expiry, whatever the label says', () => {
    const day = (date: string, label: string, expiry: boolean) => ({
      date,
      isSession: true,
      events: [
        {
          instrumentId: null,
          symbol: null,
          event: { ...AHEAD0, date, kind: 'market_structure', label, expiry },
        },
      ],
    });
    const flagged = {
      ...CALENDAR_FIXTURE,
      days: [day('2026-12-18', 'Opex', true), day('2026-12-31', 'Quarterly expiry roll', false)],
    };
    expect(calendarDays(flagged).ruledDays).toEqual(['2026-12-18']);
  });

  it('has no Market column when nothing is market-wide', () => {
    const own = { ...CALENDAR_FIXTURE, days: [DAY1] };
    expect(calendarDays(own).names.map((n) => n.symbol)).toEqual(['AAPL', 'NVDA']);
  });
});
