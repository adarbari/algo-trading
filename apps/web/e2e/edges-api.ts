/**
 * Playwright route mock for the edges: the `EdgesPage`, `ScreenerTrackRecords`, `EdgeDesk` and `EdgePaper` (nothing followed, no paper record) GraphQL
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

export interface EdgesMock {
  /** The documents the builder saved, in order, by edge id. */
  saves: { id: string; document: Record<string, unknown> }[];
}

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
    const body = route.request().postDataJSON() as { query?: string } | null;
    const query = body?.query ?? '';
    if (/query\s+EdgesPage\b/.test(query)) {
      const all = EDGES as EdgesPageData;
      await route.fulfill({
        json: { ...all, data: { ...all.data, edges: [...all.data.edges, ...copies] } },
      });
    } else if (/query\s+EdgeBuilder\b/.test(query)) {
      await route.fulfill({ json: { data: { edge: BUILDER } } });
    } else if (/query\s+EdgeDesk\b/.test(query)) {
      await route.fulfill({ json: { data: { edgeDesk: null } } });
    } else if (/query\s+EdgePaper\b/.test(query)) {
      await route.fulfill({ json: { data: { edgePaper: null } } });
    } else if (/query\s+ScreenerTrackRecords\b/.test(query)) {
      await route.fulfill({ json: { data: trackRecords() } });
    } else {
      await route.fallback();
    }
  });
  return mock;
}
