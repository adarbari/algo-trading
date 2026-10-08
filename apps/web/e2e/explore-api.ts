/**
 * Playwright route mocks for the Explore page: every `/api/*` call it makes answered from
 * fixtures recorded from the real API (e2e/fixtures/explore/, AAPL / MSFT / NVDA on
 * 2026-10-02), the GraphQL reads (`POST /api/graphql`) by operation name and key: the detail
 * pane's operations answer for AAPL from its recorded values, history, events, bars and chain
 * (feature values and history picked by the names asked). The feature table (`FeatureTable`)
 * answers like the server: the universe padded with synthetic tickers to the real size
 * (11,427), filtered, sorted (missing values last) and paged; with `keys`, those tickers in
 * that order. `ComparePrices` answers the compare set's recorded closes.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

import {
  FAMILIES,
  guideEpisode,
  guideIndicator,
  guidePlaybook,
  guideSituation,
  linked,
  REGIME_INDEX,
  SITUATION,
} from './guide-pages-api';
import { guideSearch, guideStartPage, guideTerm, START_INDEX } from './guide-start-api';

type Json = Record<string, unknown>;
type Row = Record<string, unknown>;

const fixture = (name: string): Json =>
  JSON.parse(
    readFileSync(fileURLToPath(new URL(`./fixtures/explore/${name}`, import.meta.url)), 'utf8'),
  ) as Json;

export const UNIVERSE_SIZE = 11_427;

const tickers = fixture('tickers.json');
const seedRows = (tickers['page'] as { items: Row[] }).items;

/** The recorded rows plus synthetic ones (`ZZ00001`, ...) up to the universe size. */
function universe(): Row[] {
  const rows = [...seedRows];
  const template = seedRows[0] ?? {};
  for (let i = rows.length; i < UNIVERSE_SIZE; i += 1) {
    const symbol = `ZZ${String(i).padStart(5, '0')}`;
    rows.push({
      ...template,
      instrument_id: `EQ:${symbol}`,
      symbol,
      company_name: `Synthetic ${i} Inc`,
      security_type: i % 3 === 0 ? 'ETF' : 'COMMON_STOCK',
      'rollup.price_stats@v2.close': 10 + (i % 500),
      'rollup.iv30@v1.iv30': i % 7 === 0 ? null : 0.1 + (i % 90) / 100,
    });
  }
  return rows.sort((a, b) => String(a['symbol']).localeCompare(String(b['symbol'])));
}

const ROWS = universe();
const BY_SYMBOL = new Map(ROWS.map((r) => [String(r['symbol']), r]));

/** The compare fixture's values by instrument id and feature (the dimensions). */
const COMPARED = new Map<string, Record<string, unknown>>();
for (const row of (fixture('compare.json') as { rows: { feature: string; values: Row }[] }).rows) {
  for (const [id, value] of Object.entries(row.values)) {
    COMPARED.set(id, { ...(COMPARED.get(id) ?? {}), [row.feature]: value });
  }
}

/** The recorded catalogue (`FeatureCatalogue`) by name: a column's info comes from it. */
const CATALOGUE = new Map(
  (fixture('catalogue.json') as { data: { catalogue: Row[] } }).data.catalogue.map((f) => [
    String(f['name']),
    f,
  ]),
);

/** The recorded fixtures predate `pct_from_high_avail`: it reads as the 52-week one. */
const AVAIL = 'feature.pct_from_high_avail';
const HIGH_52W = 'feature.pct_from_high_52w';

function columnInfo(name: string): Json {
  const feature = CATALOGUE.get(name === AVAIL ? HIGH_52W : name);
  return {
    name,
    description: feature?.['description'] ?? name,
    format: feature?.['format'] ?? 'NUMBER',
    unit: feature?.['unit'] ?? null,
    dtype: feature?.['dtype'] ?? 'float',
    nullMeaning: feature?.['nullMeaning'] ?? '',
    licence: feature?.['licence'] ?? 'open',
    scope: feature?.['scope'] ?? 'site',
  };
}

const valueOf = (row: Row, name: string): unknown =>
  row[name === AVAIL ? HIGH_52W : name] ??
  COMPARED.get(String(row['instrument_id']))?.[name] ??
  null;

function compare(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b));
}

/** `FeatureTable`: filtered, sorted (missing last, ties by symbol) and paged like the server. */
function featureTable(variables: Record<string, unknown>): Json {
  const columns = (variables['columns'] as string[] | undefined) ?? [];
  const keys = variables['keys'] as string[] | null | undefined;
  const sort = (variables['sort'] as string | null | undefined) ?? (keys ? null : 'symbol');
  const size = Number(variables['size'] ?? 100);
  const page = Number(variables['page'] ?? 1);
  let rows = keys ? keys.flatMap((k) => (BY_SYMBOL.has(k) ? [BY_SYMBOL.get(k) as Row] : [])) : ROWS;
  const type = variables['securityType'];
  if (type) rows = rows.filter((r) => r['security_type'] === type);
  if (variables['optionable'] === true) rows = rows.filter((_, i) => i % 2 === 0);
  const q = ((variables['q'] as string | null | undefined) ?? '').toLowerCase();
  if (q) {
    rows = rows.filter((r) =>
      `${String(r['symbol'])} ${String(r['company_name'])}`.toLowerCase().includes(q),
    );
  }
  if (sort) {
    const column = sort.replace(/^-/, '');
    const sign = sort.startsWith('-') ? -1 : 1;
    const key = (r: Row) => (column === 'symbol' ? r['symbol'] : valueOf(r, column));
    rows = [...rows].sort((a, b) => {
      const [x, y] = [key(a), key(b)];
      if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
      return sign * compare(x, y) || compare(a['symbol'], b['symbol']);
    });
  }
  const shown = keys ? rows : rows.slice((page - 1) * size, page * size);
  return {
    data: {
      table: {
        session: { date: tickers['session'], missing: [] },
        universeSnapshot: keys ? null : tickers['snapshot_date'],
        preSnapshot: false,
        sort,
        total: rows.length,
        page: keys ? 1 : page,
        size: keys ? 100 : size,
        missing: [],
        columns: columns.map(columnInfo),
        instruments: shown.map((r) => ({
          instrumentId: r['instrument_id'],
          symbol: r['symbol'],
          name: r['company_name'],
        })),
        rows: shown.map((r) => columns.map((c) => valueOf(r, c))),
        unknown: shown.map((r) => columns.map((c) => (valueOf(r, c) === null ? 'NULL' : null))),
        reasons: shown.map(() => columns.map(() => null)),
      },
    },
  };
}

const PRICES = fixture('prices.json') as {
  instruments: { instrument_id: string; symbol: string }[];
  dates: string[];
  series: Record<string, (number | null)[]>;
};

/** `ComparePrices`: the recorded closes of the tickers asked, in order. */
function comparePrices(variables: Record<string, unknown>): Json {
  const keys = (variables['keys'] as string[] | undefined) ?? [];
  const instruments = keys.flatMap((symbol) => {
    const known = PRICES.instruments.find((i) => i.symbol === symbol);
    if (!known) return [];
    const closes = PRICES.series[known.instrument_id] ?? [];
    const bars = PRICES.dates.map((session, i) => ({ session, close: closes[i] ?? null }));
    return [{ instrumentId: known.instrument_id, symbol, prices: { bars } }];
  });
  return { data: { table: { instruments } } };
}

const DISTRIBUTIONS: Record<string, string> = {
  'instrument.sector': 'dist-sector.json',
  'feature.liquidity_class': 'dist-liquidity.json',
  'instrument.security_type': 'dist-type.json',
};

interface Operation {
  query?: string;
  variables?: Record<string, unknown>;
}

const VALUES = fixture('values-aapl.json') as {
  session: string;
  instrumentId: string;
  values: Record<string, Json>;
};
const HISTORY = fixture('history-aapl.json') as {
  names: string[];
  points: { session: string; values: unknown[] }[];
};

const asked = (operation: Operation): string[] =>
  (operation.variables?.['names'] as string[] | undefined) ?? [];

/** The recorded values of the names asked, in order (a name not recorded is UNKNOWN). */
function featureValues(names: readonly string[]): Json[] {
  return names.map(
    (name) =>
      VALUES.values[name] ?? {
        name,
        value: null,
        unknown: { code: 'NULL', detail: `${name} not recorded` },
        info: { format: 'NUMBER', unit: null, dtype: 'float', nullMeaning: '' },
      },
  );
}

/** The recorded history of the names asked, each point's values in that order. */
function featureHistory(names: readonly string[]): Json {
  const at = names.map((n) => HISTORY.names.indexOf(n));
  const points = HISTORY.points.map((p) => ({
    session: p.session,
    values: at.map((i) => (i < 0 ? null : (p.values[i] ?? null))),
  }));
  return { names, points };
}

/**
 * The recorded catalogue predates the field guide: three fields get a synthetic entry (the
 * Guide's themes, how to read it, criteria and caveats).
 */
const GUIDES: Record<string, Json> = {
  'rollup.iv30@v1.iv30': {
    theme: 'implied volatility',
    reads:
      'Our 30-day at-the-money implied volatility, annualised: 0.25 means the options price a one-standard-deviation move of about 7% over the next month. Compare it with the name’s own history, not across sectors.',
    caveats: [
      'Earnings inside the 30 days lift it without the stock being rich; check rollup.earnings@v1.days_to_earnings.',
    ],
    sources: ['Cboe chains, interpolated in total variance (ADR 0021).'],
    uses: [
      {
        intent: 'Rich premium to sell',
        op: 'gte',
        value: 0.4,
        mode: 'soft',
        tolerance: 0.05,
        onMiss: null,
        note: 'Pair it with iv_hv_ratio above 1.25.',
      },
      {
        intent: 'Cheap options to buy',
        op: 'lte',
        value: 0.2,
        mode: 'hard',
        tolerance: null,
        onMiss: null,
        note: 'A filter for strategies that buy options.',
      },
    ],
  },
  'feature.iv_hv_ratio': {
    theme: 'implied volatility',
    reads: 'IV30 over HV30: above 1 the options price more movement than the stock has delivered.',
    caveats: [],
    sources: [],
    uses: [],
  },
  'rollup.price_stats@v2.hv30': {
    theme: 'volatility',
    reads: 'Realised volatility of the last 30 sessions, annualised.',
    caveats: ['A single gap day dominates a 30-session window.'],
    sources: [],
    uses: [],
  },
};

/** A guide entry with its `summary`, the first sentence of `reads` (the server's split, mocked). */
function withSummary(guide: Json | undefined): Json | null {
  if (!guide) return null;
  const reads = typeof guide['reads'] === 'string' ? guide['reads'] : '';
  return { ...guide, summary: reads.split(/(?<=[.!?])\s+(?=[A-Z0-9])/)[0] };
}

/** The recorded catalogue with the synthetic guide entries. */
function catalogue(): Json {
  const recorded = fixture('catalogue.json') as { data: { catalogue: Row[] } };
  return {
    data: {
      catalogue: recorded.data.catalogue.map((f) => ({
        ...f,
        guide: withSummary(GUIDES[String(f['name'])]),
      })),
    },
  };
}

interface GuideUse {
  intent: string;
  op: string;
  value: number;
}

/** What each guide use of the field passes, from the bins whose lower edge passes (a mock of the server's count). */
function passing(name: string, histogram: { lo: number; count: number }[]): Json[] {
  const uses = (GUIDES[name]?.['uses'] ?? []) as GuideUse[];
  return uses.map((use) => {
    const bins = histogram.map((b) =>
      (use.op === 'gte' ? b.lo >= use.value : b.lo <= use.value) ? b.count : 0,
    );
    return { intent: use.intent, count: bins.reduce((a, b) => a + b, 0), bins };
  });
}

/** `GuideHelpField`: a field's info with its guide entry (null without one), `summary` its first sentence (the server's split, mocked). */
function guideHelp(name: string): Json {
  const guide = withSummary(GUIDES[name]);
  return {
    data: {
      guideField: {
        info: {
          name,
          unit: CATALOGUE.get(name)?.['unit'] ?? null,
          guide,
        },
      },
    },
  };
}

/** A feature's distribution: the recorded one for its name, else IV30's renamed. */
function distribution(name: string): Json {
  const answer = fixture(DISTRIBUTIONS[name] ?? 'dist-iv30.json') as {
    data: { distribution: { histogram: { lo: number; count: number }[] } & Json };
  };
  const recorded = answer.data.distribution;
  return {
    data: { distribution: { ...recorded, name, passing: passing(name, recorded.histogram) } },
  };
}

/** `Query.guideIndex` for the three guided fields: the sections, theme groups and intents. */
function guideIndex(): Json {
  const intents = Object.values(GUIDES).flatMap((g) =>
    (g['uses'] as GuideUse[]).map((u) => u.intent),
  );
  return {
    data: {
      guideIndex: {
        startPages: START_INDEX.startPages,
        terms: START_INDEX.terms,
        sections: [
          START_INDEX.sections[0],
          {
            id: 'regime',
            title: 'Market regime',
            purpose: 'The indicators behind the weather and the falls they are judged on.',
            entries: REGIME_INDEX.indicators.length + REGIME_INDEX.episodes.length,
          },
          { id: 'playbooks', title: 'Playbooks', purpose: 'One page per site screen.', entries: 2 },
          { id: 'fields', title: 'Fields', purpose: 'Every catalogue field.', entries: 3 },
          {
            id: 'situations',
            title: 'Situations',
            purpose: 'States that fool fields.',
            entries: 1,
          },
          START_INDEX.sections[1],
        ],
        families: FAMILIES,
        indicators: REGIME_INDEX.indicators,
        episodes: REGIME_INDEX.episodes,
        situations: [{ name: SITUATION.name, fields: 1, slug: SITUATION.slug }],
        themeGroups: [
          {
            id: 'chart',
            title: 'The chart',
            themes: [{ theme: 'volatility', fields: 1 }],
          },
          {
            id: 'options',
            title: 'Options',
            themes: [{ theme: 'implied volatility', fields: 2 }],
          },
        ],
        intents: intents.map((intent) => ({ intent, fields: 1 })),
      },
    },
  };
}

/** `Query.guideField`: the server-derived parts of a field's page (a mock of the related reads). */
function guideField(name: string): Json {
  const known = name in GUIDES;
  if (!known)
    return { errors: [{ message: `unknown feature ${name}` }], data: { guideField: null } };
  const guide = GUIDES[name] ?? {};
  const names = [...CATALOGUE.keys()];
  return {
    data: {
      guideField: {
        readsLinked: linked(typeof guide['reads'] === 'string' ? guide['reads'] : '', names),
        caveatsLinked: ((guide['caveats'] ?? []) as string[]).map((c) => linked(c, names)),
        related: name === 'rollup.iv30@v1.iv30' ? ['feature.iv_hv_ratio'] : [],
        playbooks: [
          {
            id: 'vrp_scanner',
            name: 'VRP scanner',
            family: 'income',
            rules: ['gte 0.4 soft tolerance 0.05'],
            column: false,
            rank: false,
            flag: false,
          },
        ],
        situations: [
          {
            name: SITUATION.name,
            slug: SITUATION.slug,
            signsLinked: linked(SITUATION.signs, []),
          },
        ],
      },
    },
  };
}

/**
 * A GraphQL operation's recorded answer (`{ data }`): the catalogue (`FeatureCatalogue`), a
 * feature's distribution (`FeatureDistribution`) and AAPL's detail pane.
 */
function graphqlAnswer(operation: Operation): Json | null {
  const name = /query\s+(\w+)/.exec(operation.query ?? '')?.[1];
  if (name === 'FeatureCatalogue') return catalogue();
  if (name === 'GuideIndex') return guideIndex();
  if (name === 'GuidePlaybook') return guidePlaybook(String(operation.variables?.['id']));
  if (name === 'GuideIndicator') return guideIndicator(String(operation.variables?.['key']));
  if (name === 'GuideEpisode') return guideEpisode(String(operation.variables?.['slug']));
  if (name === 'GuideSituation') return guideSituation(String(operation.variables?.['slug']));
  if (name === 'GuideStartPage') return guideStartPage(String(operation.variables?.['id']));
  if (name === 'GuideTerm') return guideTerm(String(operation.variables?.['id']));
  if (name === 'GuideSearch') {
    return guideSearch(String(operation.variables?.['q']), Number(operation.variables?.['limit']));
  }
  if (name === 'GuideField') return guideField(String(operation.variables?.['name']));
  if (name === 'FeatureDistribution') return distribution(String(operation.variables?.['name']));
  if (name === 'GuideHelpField') return guideHelp(String(operation.variables?.['name']));
  if (name === 'FeatureTable') return featureTable(operation.variables ?? {});
  if (name === 'ComparePrices') return comparePrices(operation.variables ?? {});
  if (operation.variables?.['key'] !== 'AAPL') return null;
  const instrumentId = VALUES.instrumentId;
  switch (name) {
    case 'InstrumentFacts':
      return withEpisodeFeatures(fixture('facts-aapl.json'));
    case 'InstrumentEvents':
      return fixture('gql-events-aapl.json');
    case 'InstrumentScreenerHits':
      return {
        data: {
          session: { date: VALUES.session },
          instrument: {
            instrumentId,
            symbol: 'AAPL',
            screenerHits: [
              {
                screener: { id: 'vrp_scanner', name: 'VRP scanner' },
                result: {
                  rank: 3,
                  decision: 'WATCH',
                  score: 72,
                  reasons: 'iv_hv_ratio 1.10 below 1.25',
                  flags: [],
                  change: 'new',
                },
              },
            ],
          },
        },
      };
    case 'InstrumentPrices':
      return fixture('gql-prices-aapl.json');
    case 'InstrumentFeatureValues':
      return {
        data: {
          session: { date: VALUES.session },
          instrument: { instrumentId, features: featureValues(asked(operation)) },
        },
      };
    case 'InstrumentHistory':
      return { data: { instrument: { instrumentId, series: featureHistory(asked(operation)) } } };
    case 'OptionChain':
      return {
        data: {
          instrument: {
            instrumentId,
            symbol: 'AAPL',
            features: featureValues(asked(operation)),
            chain: fixture('gql-chain-aapl.json'),
          },
        },
      };
    case 'OptionQuotes': {
      const expiry = operation.variables['expiry'];
      const quotes = (fixture('gql-quotes-aapl.json') as unknown as Json[]).filter(
        (q) => q['expiry'] === expiry,
      );
      return { data: { instrument: { instrumentId, chain: { quotes } } } };
    }
    default:
      return null;
  }
}

function answer(url: URL, body: string | null): Json | Json[] | null {
  const path = url.pathname.replace(/^\/api/, '');
  if (path === '/graphql') return graphqlAnswer(JSON.parse(body ?? '{}') as Operation);
  return null;
}

/**
 * The recorded facts predate `episode_behaviour@v1`: the "In rough markets" values are
 * synthetic (a beta, two episodes with a drawdown, one with none stored).
 */
function withEpisodeFeatures(facts: Json): Json {
  const value = (
    name: string,
    v: unknown,
    format: string,
    unit: string,
    unknown: Json | null = null,
  ) => ({
    name: `rollup.episode_behaviour@v1.${name}`,
    value: v,
    unknown,
    info: { format, unit, dtype: 'float', nullMeaning: 'not enough bars for the episode' },
  });
  const data = facts['data'] as { instrument: { features: unknown[] } };
  data.instrument.features.push(
    value('beta_252d', 1.18, 'NUMBER', 'ratio'),
    value('dd_tariffs_2025', -0.24, 'PERCENT', 'decimal'),
    value('recovery_sessions_tariffs_2025', 41, 'NUMBER', 'sessions'),
    value('dd_hikes_2022', -0.31, 'PERCENT', 'decimal'),
    value('dd_covid_2020', null, 'PERCENT', 'decimal', {
      code: 'NO_PARTITION',
      detail: 'rollups/instrument/episode_behaviour@v1',
    }),
  );
  return facts;
}

/** Answers the Explore API from fixtures; anything else is a 404 with a detail. */
export async function mockExploreApi(page: Page): Promise<void> {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const body = answer(url, route.request().postData());
    await route.fulfill(
      body === null
        ? { status: 404, json: { detail: `no fixture for ${url.pathname}` } }
        : { status: 200, json: body },
    );
  });
}
