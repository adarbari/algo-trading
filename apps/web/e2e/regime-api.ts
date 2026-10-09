/**
 * Playwright route mock for the market regime: the `Regime`, `RegimeBands`, `RegimeEpisodes` and
 * `MarketHistory` GraphQL operations (POST /api/graphql). `Regime` and `RegimeBands` answer from
 * fixtures recorded from the real API on the golden store (e2e/fixtures/regime/): the regime is
 * UNKNOWN (`NO_PARTITION`: the golden store holds no regime rows) with its eight indicator cards
 * (range, threshold, how-line and sources included), and the band history is one UNKNOWN band.
 * `RegimeSignals` is synthetic too (`signalsAnswer`: the golden store holds no verdicts; every
 * state shows: led, still on, late, never fired, unknown with its reason). `MarketHistory` is synthetic (the golden store holds no market history; `seriesHistory`). `RegimeEpisodes` answers with the episodes and recessions
 * the real loader serves over `episodes.toml` for a 2026 session (`regime-episodes.json`; the
 * golden session of 2022 would not know the 2025 episode). Any other
 * operation falls through to the other areas' mocks. `mockRegimeComputed` serves the same
 * regime as a computed CAUTION one (the RG3 groups are not stored yet) and `mockExplain` the
 * `POST /regime/explain` of an API with a text model (the empty probe answers 400, the
 * question an explanation) or without one (503): the explain button's availability.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

const fixture = (name: string): unknown =>
  JSON.parse(
    readFileSync(fileURLToPath(new URL(`./fixtures/regime/${name}.json`, import.meta.url)), 'utf8'),
  );

const REGIME = fixture('regime');
const BANDS = fixture('regime-bands');
const EPISODES = fixture('regime-episodes');

interface Timing {
  indicator: string;
  kind: 'FAST' | 'SLOW' | 'GATE';
  state: 'LED' | 'LATE' | 'NEVER_FIRED' | 'UNKNOWN';
  flaggedDay: number | null;
  clearedDay: number | null;
  flaggedDayFromTrough: number | null;
  firstKnownDay: number | null;
  neverFired: boolean;
  unknownReason: unknown;
}

const NOT_STORED = {
  code: 'NO_ROW',
  kind: 'NOT_STORED',
  guideTerm: 'unavailable_not_stored',
  kindText: 'not stored for this session',
  cause: null,
};

/**
 * A synthetic `RegimeSignals` answer: for every episode of the fixture the gate and the eight
 * cards, cycling through the states (the first led and cleared, one still on, one late, one never
 * fired, one unknown with its reason) so the page draws each. Days are sessions from the peak.
 */
function signalsAnswer(): unknown {
  const episodes = (EPISODES as { data: { regime: { episodes: { key: string }[] } } }).data.regime
    .episodes;
  const cards = (REGIME as { data: { regime: { indicators: { key: string; pace: string }[] } } })
    .data.regime.indicators;
  const timing = (
    indicator: string,
    kind: Timing['kind'],
    state: Timing['state'],
    days: [number | null, number | null],
  ): Timing => ({
    indicator,
    kind,
    state,
    flaggedDay: days[0],
    clearedDay: days[1],
    flaggedDayFromTrough: state === 'LATE' ? 10 : null,
    firstKnownDay: null,
    neverFired: state === 'NEVER_FIRED',
    unknownReason: state === 'UNKNOWN' ? NOT_STORED : null,
  });
  const states: [Timing['state'], [number | null, number | null]][] = [
    ['LED', [-60, 30]],
    ['LED', [-15, null]],
    ['LATE', [45, 90]],
    ['NEVER_FIRED', [null, null]],
    ['UNKNOWN', [null, null]],
  ];
  return {
    data: {
      regime: {
        episodes: episodes.map((episode, e) => ({
          key: episode.key,
          signals: {
            gate: timing('gate', 'GATE', 'LED', [-5 - e, 60]),
            indicators: cards.map((card, i) => {
              const [state, days] = states[(i + e) % states.length] as (typeof states)[number];
              return timing(card.key, card.pace === 'slow' ? 'SLOW' : 'FAST', state, days);
            }),
          },
        })),
      },
    },
  };
}

interface HistoryVariables {
  names: string[];
  start: string;
  end: string;
  points: number;
}

/**
 * A synthetic `MarketHistory` answer (the golden store holds no market history): a smooth line
 * for a number (with a gap and in at most `points` points), a verdict flag that is ON for a
 * stretch around 2008, and a regime label that climbs from CALM to CRISIS and back. Enough for
 * the page to draw its charts, lanes and keys; the shapes are the real API's.
 */
function seriesHistory(name: string, { start, end, points }: HistoryVariables): unknown {
  if (name.endsWith('_on') || name.endsWith('.label')) {
    const label = name.endsWith('.label');
    const runs: [string, string, string][] = label
      ? [
          ['CALM', '2005-01-03', '2007-12-31'],
          ['CAUTION', '2008-01-02', '2008-08-29'],
          ['CRISIS', '2008-09-02', '2009-03-31'],
          ['CALM', '2009-04-01', '2026-10-02'],
        ]
      : [
          ['OFF', '2005-01-03', '2007-12-31'],
          ['ON', '2008-01-02', '2009-03-31'],
          ['OFF', '2009-04-01', '2026-10-02'],
        ];
    return {
      name,
      bucketSessions: 1,
      points: [],
      segments: runs
        .filter(([, from, to]) => to >= start && from <= end)
        .map(([value, from, to]) => ({
          start: from < start ? start : from,
          end: to > end ? end : to,
          value,
        })),
    };
  }
  const first = Date.parse(`${start}T00:00:00Z`);
  const last = Date.parse(`${end}T00:00:00Z`);
  const count = Math.min(points, 120);
  const line = Array.from({ length: count }, (_, i) => {
    const t = first + ((last - first) * i) / Math.max(1, count - 1);
    return {
      session: new Date(t).toISOString().slice(0, 10),
      value: i === 7 ? null : Math.round((50 + 30 * Math.sin(i / 9)) * 100) / 100,
    };
  });
  return { name, bucketSessions: 5, points: line, segments: [] };
}

export async function mockRegimeApi(page: Page): Promise<void> {
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as {
      query?: string;
      variables?: HistoryVariables;
    } | null;
    const query = body?.query ?? '';
    if (/query\s+MarketHistory\b/.test(query) && body?.variables) {
      const variables = body.variables;
      await route.fulfill({
        json: {
          data: { market: { history: variables.names.map((n) => seriesHistory(n, variables)) } },
        },
      });
    } else if (/query\s+RegimeSignals\b/.test(query))
      await route.fulfill({ json: signalsAnswer() });
    else if (/query\s+RegimeBands\b/.test(query)) await route.fulfill({ json: BANDS });
    else if (/query\s+RegimeEpisodes\b/.test(query)) await route.fulfill({ json: EPISODES });
    else if (/query\s+Regime\b/.test(query)) await route.fulfill({ json: REGIME });
    else await route.fallback();
  });
}

/** The regime fixture as a computed one (each value mid-range), so the page offers to explain it. */
export async function mockRegimeComputed(page: Page): Promise<void> {
  const regime = (REGIME as { data: { regime: Record<string, unknown> } }).data.regime;
  const indicators = (regime.indicators as { range: { min: number; max: number } }[]).map(
    (indicator) => ({
      ...indicator,
      value: (indicator.range.min + indicator.range.max) / 2,
      unknown: null,
    }),
  );
  const computed = {
    data: {
      regime: {
        ...regime,
        label: 'CAUTION',
        headline: '2 of 4 slow-moving warning signs are on.',
        indicators,
      },
    },
  };
  await page.route('**/api/graphql', async (route: Route) => {
    const query = (route.request().postDataJSON() as { query?: string } | null)?.query ?? '';
    if (/query\s+Regime\b/.test(query)) await route.fulfill({ json: computed });
    else await route.fallback();
  });
}

export const EXPLANATION = {
  text: 'Clouds are building: two slow warning signs are on.',
  citations: [{ title: 'FRED: T10Y3M', url: 'https://fred.stlouisfed.org/series/T10Y3M' }],
  checked: true,
  note: null,
  cached: false,
};

/** `POST /api/regime/explain` of an API with a text model (`on`) or without one. */
export async function mockExplain(page: Page, on: boolean): Promise<void> {
  await page.route('**/api/regime/explain', async (route: Route) => {
    const body = route.request().postDataJSON() as { question: string | null; card: string | null };
    if (!on) {
      await route.fulfill({
        status: 503,
        json: { detail: 'the text model is off: enable it in config/site/llm.toml (ADR 0041)' },
      });
    } else if (body.question === null && body.card === null) {
      await route.fulfill({ status: 400, json: { detail: 'ask one of question or card' } });
    } else {
      await route.fulfill({ json: EXPLANATION });
    }
  });
}
