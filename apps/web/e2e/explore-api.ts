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

const CATALOGUE = new Map(
  (fixture('features.json') as unknown as Row[]).map((f) => [String(f['name']), f]),
);

/** The server's display format from a feature's unit and dtype (catalogue.format_of). */
function formatOf(feature: Row | undefined): string {
  const unit = feature?.['unit'];
  const dtype = (feature?.['dtype'] as string | undefined) ?? 'float';
  if (dtype === 'date' || unit === 'date') return 'DATE';
  if (dtype === 'bool') return 'FLAG';
  if (dtype === 'str') return 'TEXT';
  if (unit === 'decimal') return 'PERCENT';
  if (unit === 'usd_per_share') return 'CURRENCY';
  if (unit === 'usd' || unit === 'shares') return 'COMPACT';
  return 'NUMBER';
}

function columnInfo(name: string): Json {
  const feature = CATALOGUE.get(name);
  return {
    name,
    description: feature?.['description'] ?? name,
    format: formatOf(feature),
    unit: feature?.['unit'] ?? null,
    dtype: feature?.['dtype'] ?? 'float',
    nullMeaning: feature?.['null_meaning'] ?? '',
    licence: feature?.['licence'] ?? 'open',
    scope: feature?.['scope'] ?? 'site',
  };
}

const valueOf = (row: Row, name: string): unknown =>
  row[name] ?? COMPARED.get(String(row['instrument_id']))?.[name] ?? null;

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
  if (name === 'FeatureTable') return featureTable(operation.variables ?? {});
  if (name === 'ComparePrices') return comparePrices(operation.variables ?? {});
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
