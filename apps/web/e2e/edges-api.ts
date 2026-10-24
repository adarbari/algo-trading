/**
 * Playwright route mock for the edges: the `EdgesPage` (the list: rows with their `summary`), `EdgeDetail` (one edge in full), `EdgeDocument` (the builder's one-edge read), `ScreenerTrackRecords`, `EdgeDesk` and `EdgePaper` (nothing followed, no paper record)
 * and the result sections (`EdgeResultCurve`, `EdgeResultDrawdown`, `EdgeResultDecay`, the regimes,
 * holding periods, costs, capacity, rolling starts and monthly map, `EdgeTrades`, `EdgeVariantGrid`) GraphQL
 * operations (POST /api/graphql). The golden store holds no edge runs, so the answers are
 * synthetic with the real API's shapes (`Query.edges`, `Screener.trackRecords`): one candidate
 * edge with an official result and an exploratory run beside it, one rejected edge with no
 * result; the VRP screeners (Ideas and Screeners ids) are candidates with their record, every other
 * screener has none. The builder's writes are stateful: a copy (`POST /edges/{id}/copy`) joins the
 * list as the user's own edge, `PUT /edges/{id}` is recorded in the returned `saves`, and the
 * `EdgeBuilder` read answers with the settings the API resolves. Any other operation falls
 * through to the other areas' mocks.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

interface TrackRecords {
  data: { edges: unknown[]; screeners: { trackRecords: Record<string, unknown>[] }[] };
}

const load = (name: string): unknown =>
  JSON.parse(
    readFileSync(fileURLToPath(new URL(`./fixtures/edges/${name}`, import.meta.url)), 'utf8'),
  );

const EDGES = load('edges-page.json');
const RECORDS = load('track-records.json') as TrackRecords;

// What `Query.edge(id)` resolves for the builder: the copy's settings and its own document.
const BUILDER = {
  schedule: 'month_end',
  frozenFrom: '2026-04-01',
  replaces: null,
  settings: {
    topK: 50,
    universe: 'liquid_common_stocks',
    kind: 'excess_return',
    benchmark: 'SPY',
    startOffsetSessions: 1,
    costBps: 10,
    qualityBar: [
      'outcome',
      'trigger_timing',
      'replication',
      'expected_size',
      'capacity_costs',
      'failure_modes',
      'decoys',
    ].map((key) => ({ key, text: `The ${key} answer.` })),
    own: { extends: 'momentum_12_1' },
  },
};

// The result sections of momentum_12_1 as `Query.edgeResult` answers them: a curve with both sides
// of the split and a gap, a drawdown with one open episode, and a decay with the paper's bar not given.
const CURVE = {
  kind: 'cumulative_excess',
  unit: 'return',
  splitFrom: '2026-04-01',
  hidden: false,
  points: [
    ['2026-01-02', '2026-02-02', 'in_sample', 0.01, 0.01, 0.002],
    ['2026-03-02', '2026-04-02', 'in_sample', 0.02, 0.03, 0.004],
    ['2026-05-04', '2026-06-03', 'out_of_sample', -0.01, 0.02, 0.006],
    ['2026-06-01', '2026-07-01', 'out_of_sample', 0.015, 0.035, 0.008],
  ].map(([decision, exit, period, value, cumulative, baseCumulative]) => ({
    decision,
    exit,
    period,
    value,
    cumulative,
    baseValue: 0.002,
    baseCumulative,
    trades: 1,
  })),
  gaps: [{ from: '2026-02-10', to: '2026-02-20', kind: 'no_picks', unknown: null }],
  baselines: [],
  live: null,
  unknown: null,
};
const DRAWDOWN = {
  unit: 'return',
  points: [
    { exit: '2026-02-02', depth: 0 },
    { exit: '2026-04-02', depth: 0 },
    { exit: '2026-06-03', depth: -0.01 },
    { exit: '2026-07-01', depth: 0 },
  ],
  episodes: [{ peak: '2026-04-02', trough: '2026-06-03', recovered: '2026-07-01', depth: 0.01 }],
  maxInSample: 0.005,
  maxOutOfSample: 0.01,
  volInSample: 0.12,
  volOutOfSample: null,
  unknown: null,
};
const DECAY = {
  measure: 'lift_pts',
  unit: 'points',
  basisHorizon: 20,
  published: null,
  bars: [
    { period: 'published', value: null, n: null, state: 'not_given' },
    { period: 'in_sample', value: 6, n: 64, state: 'measured' },
    { period: 'out_of_sample', value: 5, n: 6, state: 'measured' },
    { period: 'live', value: null, n: 0, state: 'not_measured_live' },
  ],
};

const figure = (
  period: string,
  winRate: number,
  baseRate: number,
  liftPts: number,
  trades: number,
) => ({
  period,
  state: 'measured',
  winRate,
  baseRate,
  liftPts,
  trades,
  thin: trades < 5,
});
const SLICES = (liftPts: number) => [
  figure('in_sample', 0.6, 0.55, liftPts, 12),
  figure('out_of_sample', 0.62, 0.55, liftPts, 6),
  figure('all', 0.61, 0.55, liftPts, 18),
];
// The lower sections of momentum_12_1 as the API answers them: where it worked by regime and by
// holding period, the cost strip, the capacity, the rolling starts and the monthly map.
const REGIMES = {
  state: 'measured',
  variant: 'main',
  horizon: 20,
  rows: [
    { regime: 'CALM', figures: SLICES(5) },
    { regime: 'STRESS', figures: SLICES(-2) },
  ],
};
const HORIZONS = {
  state: 'measured',
  variant: 'main',
  needed: 40,
  rows: [10, 20].map((horizon) => ({
    horizon,
    basis: horizon === 20,
    figures: SLICES(horizon === 20 ? 7 : 4),
    oosBy: {
      state: 'projected',
      needed: 40,
      have: 6,
      remaining: 34,
      expectedBy: '2027-03-15',
      fillRatio: null,
    },
  })),
};
const COSTS = {
  state: 'measured',
  variant: 'main',
  horizon: 20,
  assumedBp: 15,
  levels: [0, 15, 30].map((bp) => ({
    period: 'out_of_sample',
    bp,
    assumed: bp === 15,
    sessions: 6,
    picks: 30,
    winRate: 0.62,
    baseRate: 0.55,
    liftPts: 2 - bp / 10,
    meanExcess: 0.01,
  })),
  periods: ['in_sample', 'out_of_sample', 'all'].map((period) => ({
    period,
    state: 'measured',
    breakEvenBp: 20,
    decileSpread: 0.05,
  })),
};
const CAPACITY = {
  state: 'measured',
  variant: 'main',
  horizon: 20,
  floorUsd: 5000000,
  positionUsd: 100000,
  universeFloorUsd: null,
  floorBinds: true,
  periods: ['in_sample', 'out_of_sample', 'all'].map((period) => ({
    period,
    state: 'measured',
    picks: 30,
    advMedian: 4e8,
    advKnown: 30,
    advLow: 2,
    positionShare: 0.00025,
  })),
};
const ROLLING = {
  unit: 'points',
  starts: [
    { start: '2026-01-02', trades: 18, liftPts: 7, meanExcess: 0.01 },
    { start: '2026-04-01', trades: 6, liftPts: 5, meanExcess: 0.008 },
  ],
  unknown: null,
};
const MONTHLY = {
  unit: 'return',
  months: [
    { month: '2026-02', value: 0.01, trades: 3, period: 'in_sample' },
    { month: '2026-05', value: -0.01, trades: 2, period: 'out_of_sample' },
  ],
  unknown: null,
};
const TRADES = {
  period: 'ALL',
  page: 1,
  pageSize: 50,
  total: 2,
  basis: 'main at 20 sessions',
  licence: null,
  oosHidden: false,
  symbolsSnapshot: '2026-10-01',
  unknown: null,
  rows: [
    ['2026-05-04', 'US-AAA', 'won', 0.031],
    ['2026-02-02', 'US-BBB', 'lost', -0.012],
  ].map(([decisionSession, instrumentId, status, value]) => ({
    variant: 'main',
    horizonSessions: 20,
    decisionSession,
    entrySession: decisionSession,
    exitSession: decisionSession,
    instrumentId,
    symbol: { value: String(instrumentId).replace('US-', ''), unknown: null },
    company: { value: null, unknown: null },
    symbolAsOf: '2026-01-15',
    rank: 1,
    status,
    excludedReason: null,
    hit: status === 'won',
    delisted: false,
    beforeSplit: String(decisionSession) < '2026-04-01',
    source: 'backtest',
    score: { value: 1.2, unknown: null },
    value: { value, unknown: null },
    grossValue: { value, unknown: null },
    maxDrawdown: -0.02,
    advUsd: { value: 4e8, unknown: null },
    reference: { value: 0.01, unknown: null },
    touch: { value: null, unknown: null },
  })),
};

const TRADE_FILTER_SET = {
  filterSet: {
    surface: 'edge_trades',
    label: 'Edge trades',
    filters: [
      ['result', 'Result', 'PICK', 'term:filter_trade_result', ['won', 'Won'], ['lost', 'Lost']],
      ['in_sample', 'In sample', 'TOGGLE', 'term:filter_trade_in_sample'],
      ['record', 'Backtest or live', 'PICK', 'term:filter_trade_record', ['backtest', 'Backtest']],
    ].map(([id, label, kind, guide, ...options]) => ({
      id,
      label,
      group: 'SETUP',
      kind,
      guide,
      options: (options as string[][]).map(([value, text]) => ({ value, label: text })),
      bins: [],
      windowUnit: null,
    })),
  },
};
interface TradeInput {
  id: string;
  values: string[];
  active: boolean;
}
type TradeRowShape = (typeof TRADES.rows)[number];
const tradePasses = (row: TradeRowShape, f: TradeInput): boolean => {
  if (f.id === 'result') return f.values.includes(String(row.status));
  if (f.id === 'in_sample') return f.values.includes(row.beforeSplit ? 'yes' : 'no');
  return f.values.includes(row.source);
};

/** The ledger as the server serves it under `filters`: the rows that pass, and the counts. */
function tradesServed(filters: TradeInput[] | null) {
  const active = (filters ?? []).filter((f) => f.active);
  const passing = (others: TradeInput[]) =>
    TRADES.rows.filter((r) => others.every((f) => tradePasses(r, f)));
  const rows = passing(active);
  return {
    ...TRADES,
    total: rows.length,
    rows,
    facets: {
      total: TRADES.rows.length,
      matched: rows.length,
      items: (filters ?? []).map((f) => ({
        id: f.id,
        active: f.active,
        removes: f.active ? passing(active.filter((o) => o !== f)).length - rows.length : null,
        unknown: 0,
        options: [],
        bins: [],
      })),
    },
  };
}
const FIGS = (liftPts: number, trades: number) => ({
  winRate: 0.6,
  baseRate: 0.55,
  liftPts,
  decileSpread: 0.05,
  trades,
});
const VARIANTS = {
  basis: 'main at 20 sessions',
  trials: 3,
  oosHidden: false,
  unknown: null,
  rows: [10, 20].map((horizonSessions) => ({
    edgeVariant: 'main',
    variant: 'main',
    horizonSessions,
    inSample: FIGS(1, 12),
    outOfSample: FIGS(horizonSessions === 20 ? 7 : 4, 6),
    all: FIGS(2, 18),
    official: horizonSessions === 20,
    notPreChosen: horizonSessions !== 20,
    modelFit: false,
  })),
};
const SECTIONS: [RegExp, Record<string, unknown>][] = [
  [/query\s+EdgeResultRegimes\b/, { edgeResult: { regimes: REGIMES } }],
  [/query\s+EdgeResultHorizons\b/, { edgeResult: { horizons: HORIZONS } }],
  [/query\s+EdgeResultCosts\b/, { edgeResult: { costs: COSTS } }],
  [/query\s+EdgeResultCapacity\b/, { edgeResult: { capacity: CAPACITY } }],
  [/query\s+EdgeResultRollingStarts\b/, { edgeResult: { rollingStarts: ROLLING } }],
  [/query\s+EdgeResultMonthly\b/, { edgeResult: { monthly: MONTHLY } }],
  [/query\s+EdgeVariantGrid\b/, { edgeVariants: VARIANTS }],
];

const VRP_IDS = ['vrp-scanner', 'vrp_scanner'];

function trackRecords() {
  const first = RECORDS.data.screeners[0];
  const screeners = [
    ...VRP_IDS.map((id) => ({
      id,
      trackRecords: (first?.trackRecords ?? []).slice(0, 1).map((r) => ({ ...r, screenerId: id })),
    })),
    { id: 'short-premium-liquidity', trackRecords: [] },
  ];
  return { edges: RECORDS.data.edges.slice(0, 1), screeners };
}

/** `ScreenerEdges`: a VRP screener belongs to two edges (a candidate and an evidenced one); every other screener to none. */
function screenerEdges(id: string) {
  const first = RECORDS.data.screeners[0];
  const records = VRP_IDS.includes(id)
    ? (first?.trackRecords ?? []).map((r) => ({ ...r, screenerId: id, splitFrom: '2026-04-01' }))
    : [];
  return { edges: RECORDS.data.edges, screener: { id, trackRecords: records } };
}

export interface EdgesMock {
  /** The documents the builder saved, in order, by edge id. */
  saves: { id: string; document: Record<string, unknown> }[];
}

/** The definitions of the Edges list's filters (config/site/filters/edges.toml), trimmed. */
const EDGE_FILTER_SET = {
  surface: 'edges',
  label: 'Edges',
  filters: [
    {
      id: 'status',
      label: 'Status',
      group: 'SETUP',
      kind: 'PICK',
      guide: 'term:filter_edge_status',
      options: [
        { value: 'candidate', label: 'Candidate' },
        { value: 'rejected', label: 'Rejected' },
      ],
      bins: [],
      windowUnit: null,
    },
    {
      id: 'mine',
      label: 'Mine',
      group: 'SETUP',
      kind: 'TOGGLE',
      guide: 'term:filter_edge_mine',
      options: [],
      bins: [],
      windowUnit: null,
    },
    {
      id: 'followed',
      label: 'Following',
      group: 'SETUP',
      kind: 'TOGGLE',
      guide: 'term:filter_edge_followed',
      options: [],
      bins: [],
      windowUnit: null,
    },
  ],
};

type EdgesPageData = { data: { edges: Record<string, unknown>[] } };

/** The user's copy of the first edge, as the list serves it after the copy was made. */
function copyOf(id: string, version: boolean): Record<string, unknown> {
  const first = (EDGES as EdgesPageData).data.edges[0] as Record<string, unknown>;
  return {
    ...first,
    id,
    name: `My ${String(first['name'])}`,
    mine: true,
    extends: first['id'],
    oosHidden: true,
    state: version ? 'trial' : 'researching',
    runs: [],
    canonicalRun: null,
  };
}

export async function mockEdgesApi(page: Page): Promise<EdgesMock> {
  const mock: EdgesMock = { saves: [] };
  const copies: Record<string, unknown>[] = [];
  let polls = 0;
  await page.route('**/api/edges/*/copy', async (route: Route) => {
    const body = route.request().postDataJSON() as { new_id: string; as_version: boolean };
    copies.push(copyOf(body.new_id, body.as_version));
    await route.fulfill({ status: 201, json: { edge_id: body.new_id, document: {} } });
  });
  await page.route('**/api/edges/*', async (route: Route) => {
    if (route.request().method() !== 'PUT') return route.fallback();
    const id = new URL(route.request().url()).pathname.split('/').pop() ?? '';
    const { document } = route.request().postDataJSON() as { document: Record<string, unknown> };
    mock.saves.push({ id, document });
    return route.fulfill({ json: { edge_id: id, document } });
  });
  const evaluation = (state: string) => ({
    state,
    edge_id: 'momentum_12_1',
    kind: 'edge-eval',
    user: 'ann',
    session: null,
    job_id: 'job-edge-eval-1',
    run_id: state === 'complete' ? 'run-9' : null,
    exploratory: state === 'complete' ? true : null,
    error: null,
  });
  await page.route('**/api/edges/*/evaluate**', async (route: Route) => {
    polls = 0;
    await route.fulfill({ status: 202, json: evaluation('running') });
  });
  await page.route('**/api/jobs/*', async (route: Route) => {
    polls += 1; // the first poll still sees it running
    await route.fulfill({ json: evaluation(polls > 1 ? 'complete' : 'running') });
  });
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as {
      query?: string;
      variables?: {
        ids?: string[];
        id?: string;
        surface?: string;
        q?: string | null;
        filters?: TradeInput[] | null;
      };
    } | null;
    const query = body?.query ?? '';
    if (/query\s+FilterSet\b/.test(query) && body?.variables?.surface === 'edge_trades') {
      await route.fulfill({ json: { data: TRADE_FILTER_SET } });
      return;
    }
    if (/query\s+EdgeTrades\b/.test(query)) {
      await route.fulfill({
        json: { data: { edgeTrades: tradesServed(body?.variables?.filters ?? null) } },
      });
      return;
    }
    if (/query\s+EdgeDocument\b/.test(query)) {
      // The builder's document-only read: the listed edges (the user's copies too), no runs.
      const ids = body?.variables?.ids ?? [];
      const all = [...(EDGES as EdgesPageData).data.edges, ...copies];
      const found = all.filter((e) => ids.includes(String(e['id'])));
      await route.fulfill({
        json: { data: { edges: found.map((e) => ({ ...e, variantsTried: 0 })) } },
      });
    } else if (/query\s+EdgeDetail\b/.test(query)) {
      // One edge in full (the edge page): only the listed ids, the user's copies too.
      const ids = body?.variables?.ids ?? [];
      const all = [...(EDGES as EdgesPageData).data.edges, ...copies];
      await route.fulfill({
        json: { data: { edges: all.filter((e) => ids.includes(String(e['id']))) } },
      });
    } else if (/query\s+FilterSet\b/.test(query) && body?.variables?.surface === 'edges') {
      await route.fulfill({ json: { data: { filterSet: EDGE_FILTER_SET } } });
    } else if (/query\s+EdgeProblems\b/.test(query)) {
      const all = EDGES as EdgesPageData & { data: { edgeProblems?: unknown[] } };
      await route.fulfill({ json: { data: { edgeProblems: all.data.edgeProblems ?? [] } } });
    } else if (/query\s+EdgesPage\b/.test(query)) {
      // The list: each edge's row and the headline of its verdict, as the server's `summary`,
      // narrowed by the search and the `mine` / `followed` / `status` filters, with their counts.
      const all = EDGES as EdgesPageData;
      const needle = (body?.variables?.q ?? '').toLowerCase();
      const found = [...all.data.edges, ...copies].filter((e) =>
        [e['id'], e['name'], e['thesis']].some((t) =>
          (typeof t === 'string' ? t : '').toLowerCase().includes(needle),
        ),
      );
      const filters = (body?.variables?.filters ?? []) as {
        id: string;
        values: string[];
        active: boolean;
      }[];
      const passes = (e: Record<string, unknown>, f: { id: string; values: string[] }) =>
        f.id === 'mine'
          ? e['mine'] === true
          : f.id === 'followed'
            ? e['state'] === 'following'
            : f.id === 'status'
              ? f.values.includes(String(e['status']))
              : true;
      const kept = found.filter((e) => filters.every((f) => !f.active || passes(e, f)));
      const rows = kept.map((e) => {
        const verdict = (e['verdict'] ?? {}) as Record<string, unknown>;
        return {
          id: e['id'],
          name: e['name'],
          status: e['status'],
          state: e['state'],
          mine: e['mine'],
          screeners: e['screeners'],
          summary: {
            verdict: verdict['verdict'],
            result: verdict['result'],
            trades: verdict['trades'],
          },
        };
      });
      const statusCount = (value: string) => found.filter((e) => e['status'] === value).length;
      await route.fulfill({
        json: {
          data: {
            edgeList: {
              total: rows.length,
              items: rows,
              facets: {
                total: found.length,
                matched: rows.length,
                items: filters.map((f) => ({
                  id: f.id,
                  active: f.active,
                  removes: f.active
                    ? found.filter((e) =>
                        filters.every((g) => g === f || !g.active || passes(e, g)),
                      ).length - rows.length
                    : null,
                  unknown: 0,
                  options:
                    f.id === 'status'
                      ? ['candidate', 'rejected'].map((value) => ({
                          value,
                          count: statusCount(value),
                        }))
                      : [],
                  bins: [],
                })),
              },
            },
          },
        },
      });
    } else if (/query\s+EdgeBuilder\b/.test(query)) {
      await route.fulfill({ json: { data: { edge: BUILDER } } });
    } else if (/query\s+EdgeDesk\b/.test(query)) {
      await route.fulfill({ json: { data: { edgeDesk: null } } });
    } else if (/query\s+EdgePaper\b/.test(query)) {
      await route.fulfill({ json: { data: { edgePaper: null } } });
    } else if (/query\s+EdgeResultCurve\b/.test(query)) {
      await route.fulfill({ json: { data: { edgeResult: { curve: CURVE } } } });
    } else if (/query\s+EdgeResultDrawdown\b/.test(query)) {
      await route.fulfill({ json: { data: { edgeResult: { drawdown: DRAWDOWN } } } });
    } else if (/query\s+EdgeResultDecay\b/.test(query)) {
      await route.fulfill({ json: { data: { edgeResult: { decay: DECAY } } } });
    } else if (SECTIONS.some(([name]) => name.test(query))) {
      const [, data] = SECTIONS.find(([name]) => name.test(query)) ?? [];
      await route.fulfill({ json: { data } });
    } else if (/query\s+ScreenerEdges\b/.test(query)) {
      await route.fulfill({ json: { data: screenerEdges(body?.variables?.id ?? '') } });
    } else if (/query\s+ScreenerTrackRecords\b/.test(query)) {
      await route.fulfill({ json: { data: trackRecords() } });
    } else {
      await route.fallback();
    }
  });
  return mock;
}
