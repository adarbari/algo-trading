/**
 * Playwright route mock for the event study: the `InstrumentEventStudy` and `EventCalendar`
 * GraphQL operations (POST /api/graphql). The golden store holds no event rows, so the answers
 * are synthetic with the real API's shapes (`Instrument.eventStudy`, `Query.eventCalendar`):
 * AAPL has earnings, a CPI and an expiry ahead, two clear-or-not ladder rungs and one 8-K;
 * every other ticker is a fund tracking NVDA with no filings (NOT_APPLICABLE). The calendar has
 * a market-wide CPI, AAPL earnings and a monthly expiry Friday; with `scope` false it answers
 * for the names asked (`calendarAsked` records the variables).
 */
import type { Page, Route } from '@playwright/test';

const event = (kind: string, date: string, label: string, time: string, source: string) => ({
  date,
  time,
  kind,
  label,
  name: label,
  subjectId: null,
  source,
  knownFrom: null,
});

const CPI = event('macro_release', '2026-10-14', 'CPI', '08:30', 'BLS');
const EARNINGS = event('own_earnings', '2026-10-29', 'Earnings', 'after_hours', 'Company calendar');
const OPEX = event('market_structure', '2026-10-16', 'Monthly expiry', 'close', 'Rule');

const AAPL_STUDY = {
  session: '2026-10-07',
  days: 90,
  months: 24,
  ahead: [CPI, OPEX, EARNINGS],
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
    { expiry: '2026-10-16', days: 9, clear: false, marked: false, spans: [CPI, OPEX] },
    { expiry: '2026-10-23', days: 16, clear: true, marked: true, spans: [OPEX] },
  ],
  reference: null,
  gaps: [],
};

const FUND_STUDY = {
  ...AAPL_STUDY,
  ahead: [CPI, { ...EARNINGS, kind: 'reference_earnings', label: 'NVDA earnings' }],
  filings: [],
  ladder: [],
  reference: {
    instrumentId: 'EQ:NVDA',
    symbol: 'NVDA',
    kind: 'single_stock',
    source: 'name_rule',
    status: 'LINKED',
  },
  gaps: [
    {
      instrumentId: null,
      part: 'ladder',
      unknown: {
        code: 'NO_PARTITION',
        detail: 'no option chain stored for the session',
        reason: null,
      },
    },
    {
      instrumentId: null,
      part: 'filings',
      unknown: { code: 'NOT_APPLICABLE', detail: 'a fund files no 8-Ks', reason: null },
    },
  ],
};

const AAPL = { instrumentId: 'EQ:AAPL', symbol: 'AAPL' };
const SOXS = { instrumentId: 'EQ:SOXS', symbol: 'SOXS' };

function calendar(ids: string[], scope: boolean): unknown {
  const names = scope ? [AAPL, SOXS] : [AAPL, SOXS].filter((n) => ids.includes(n.instrumentId));
  const own = names.some((n) => n.symbol === 'AAPL');
  const day = (date: string, events: unknown[]) => ({ date, isSession: true, events });
  return {
    session: '2026-10-07',
    end: '2027-01-05',
    names,
    days: [
      day('2026-10-14', [{ instrumentId: null, symbol: null, event: CPI }]),
      day('2026-10-16', [{ instrumentId: null, symbol: null, event: OPEX }]),
      day('2026-10-29', own ? [{ ...AAPL, event: EARNINGS }] : []),
    ],
    gaps: [],
    missing: [],
    unresolved: [],
  };
}

export interface EventsMock {
  /** The variables of every `EventCalendar` read. */
  calendarAsked: { instrumentIds: string[]; scope: boolean }[];
}

export async function mockEventsApi(page: Page): Promise<EventsMock> {
  const mock: EventsMock = { calendarAsked: [] };
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as {
      query?: string;
      variables?: { key?: string; instrumentIds?: string[]; scope?: boolean };
    } | null;
    const query = body?.query ?? '';
    const variables = body?.variables ?? {};
    if (/query\s+InstrumentEventStudy\b/.test(query)) {
      const aapl = variables.key === 'AAPL';
      await route.fulfill({
        json: {
          data: {
            session: { date: '2026-10-07' },
            instrument: {
              instrumentId: aapl ? AAPL.instrumentId : `EQ:${variables.key ?? ''}`,
              symbol: variables.key,
              eventStudy: aapl ? AAPL_STUDY : FUND_STUDY,
            },
          },
        },
      });
    } else if (/query\s+EventCalendar\b/.test(query)) {
      const ids = variables.instrumentIds ?? [];
      const scope = variables.scope === true;
      mock.calendarAsked.push({ instrumentIds: ids, scope });
      await route.fulfill({ json: { data: { eventCalendar: calendar(ids, scope) } } });
    } else await route.fallback();
  });
  return mock;
}
