/**
 * Playwright route mocks for the Explore page: every `/api/*` call it makes answered from
 * fixtures recorded from the real API (e2e/fixtures/explore/, AAPL / MSFT / NVDA on
 * 2026-10-02), the GraphQL reads (`POST /api/graphql`) by operation name and key: the detail
 * pane's operations answer for AAPL from its recorded values, history, events, bars and chain
 * (feature values and history picked by the names asked). The ticker table is padded with
 * synthetic tickers to the real universe size (11,427) so the table is exercised at full
 * scale.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

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

const DISTRIBUTIONS: Record<string, string> = {
  'instrument.sector': 'dist-sector.json',
  'feature.liquidity_class': 'dist-liquidity.json',
  'instrument.security_type': 'dist-type.json',
};

function tickerPage(url: URL): Json {
  const size = Number(url.searchParams.get('size') ?? 100);
  const page = Number(url.searchParams.get('page') ?? 1);
  const type = url.searchParams.get('security_type');
  const optionable = url.searchParams.get('optionable');
  let rows = ROWS;
  if (type) rows = rows.filter((r) => r['security_type'] === type);
  if (optionable === 'true') rows = rows.filter((_, i) => i % 2 === 0);
  return {
    ...tickers,
    page: { total: rows.length, page, size, items: rows.slice((page - 1) * size, page * size) },
  };
}

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

/** A feature's distribution: the recorded one for its name, else IV30's renamed. */
function distribution(name: string): Json {
  const answer = fixture(DISTRIBUTIONS[name] ?? 'dist-iv30.json') as {
    data: { distribution: Json };
  };
  return { data: { distribution: { ...answer.data.distribution, name } } };
}

/**
 * A GraphQL operation's recorded answer (`{ data }`): the catalogue (`FeatureCatalogue`), a
 * feature's distribution (`FeatureDistribution`) and AAPL's detail pane.
 */
function graphqlAnswer(operation: Operation): Json | null {
  const name = /query\s+(\w+)/.exec(operation.query ?? '')?.[1];
  if (name === 'FeatureCatalogue') return fixture('catalogue.json');
  if (name === 'FeatureDistribution') return distribution(String(operation.variables?.['name']));
  if (operation.variables?.['key'] !== 'AAPL') return null;
  const instrumentId = VALUES.instrumentId;
  switch (name) {
    case 'InstrumentFacts':
      return fixture('facts-aapl.json');
    case 'InstrumentEvents':
      return fixture('gql-events-aapl.json');
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
  if (path === '/explore/tickers') return tickerPage(url);
  if (path === '/explore/compare') return fixture('compare.json');
  if (path === '/explore/compare/prices') return fixture('prices.json');
  return null;
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
