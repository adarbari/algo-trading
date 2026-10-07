/** Test builders for the event entity (exported for widget tests): an event study and a calendar as the API answers them. */
import type { EventCalendarResponse } from '../api/calendar';
import type { EventStudyResponse } from '../api/study';

type Study = NonNullable<NonNullable<EventStudyResponse['instrument']>['eventStudy']>;

const ahead = (kind: string, date: string, label: string, time: string, source = 'Calendar') => ({
  date,
  time,
  kind,
  label,
  name: label,
  subjectId: null,
  source,
  knownFrom: null,
});

export const STUDY_FIXTURE: Study = {
  session: '2026-10-07',
  days: 90,
  months: 24,
  ahead: [
    ahead('macro_release', '2026-10-14', 'CPI', '08:30', 'BLS'),
    ahead('own_earnings', '2026-10-29', 'Earnings', 'after_hours', 'Company calendar'),
    ahead('market_structure', '2026-11-20', 'Monthly expiry', 'close', 'Rule'),
  ],
  filings: [
    {
      accepted: '2026-07-30T20:31:00+00:00',
      filingDate: '2026-07-30',
      form: '8-K',
      items: ['2.02', '9.01'],
      label: 'Results',
      knownFrom: '2026-07-30',
    },
  ],
  ladder: [
    {
      expiry: '2026-10-16',
      days: 9,
      clear: false,
      marked: false,
      spans: [ahead('macro_release', '2026-10-14', 'CPI', '08:30', 'BLS')],
    },
    { expiry: '2026-10-23', days: 16, clear: true, marked: true, spans: [] },
  ],
  reference: null,
  gaps: [],
};

export const CALENDAR_FIXTURE: EventCalendarResponse = {
  session: '2026-10-07',
  end: '2027-01-05',
  names: [
    { instrumentId: 'EQ:A', symbol: 'AAPL' },
    { instrumentId: 'EQ:N', symbol: 'NVDA' },
  ],
  days: [
    {
      date: '2026-10-14',
      isSession: true,
      events: [
        {
          instrumentId: null,
          symbol: null,
          event: ahead('macro_release', '2026-10-14', 'CPI', '08:30', 'BLS'),
        },
      ],
    },
    {
      date: '2026-10-29',
      isSession: true,
      events: [
        {
          instrumentId: 'EQ:A',
          symbol: 'AAPL',
          event: ahead('own_earnings', '2026-10-29', 'Earnings', 'after_hours'),
        },
      ],
    },
    {
      date: '2026-11-20',
      isSession: true,
      events: [
        {
          instrumentId: null,
          symbol: null,
          event: ahead('market_structure', '2026-11-20', 'Monthly expiry', 'close', 'Rule'),
        },
      ],
    },
  ],
  gaps: [],
  missing: [],
  unresolved: [],
};
