/**
 * Playwright route mock for the edges: the `EdgesPage` and `ScreenerTrackRecords` GraphQL
 * operations (POST /api/graphql). The golden store holds no edge runs, so the answers are
 * synthetic with the real API's shapes (`Query.edges`, `Screener.trackRecords`): one candidate
 * edge with a frozen canonical run and an exploratory run beside it, one rejected edge with no
 * run; the VRP screeners (Ideas and Screeners ids) are candidates with their record, every other
 * screener has none. Any other operation falls through to the other areas' mocks.
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

export async function mockEdgesApi(page: Page): Promise<void> {
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as { query?: string } | null;
    const query = body?.query ?? '';
    if (/query\s+EdgesPage\b/.test(query)) {
      await route.fulfill({ json: EDGES });
    } else if (/query\s+ScreenerTrackRecords\b/.test(query)) {
      await route.fulfill({ json: { data: trackRecords() } });
    } else {
      await route.fallback();
    }
  });
}
