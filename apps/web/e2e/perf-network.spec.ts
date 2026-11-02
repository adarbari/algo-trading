/**
 * The distant-client budgets (owner ask 2026-10-21): each main route's first load over a modelled
 * link of 280 ms round trip and 10 Mbit/s down (scripts/network/model.ts, the profile of a user
 * in India reaching the owner's Mac behind Tailscale Funnel), the API mocked as in the other
 * specs. Every response is held back by the model before the browser sees it: the static files
 * as gzip (the real server compresses; `vite preview` does not) with their gzip size on the
 * link, the API with its round trip (the mocks' bodies are fixtures, so API bytes are reported,
 * not modelled; real sizes: `scripts/perf/payload_sizes.py` against a spare API).
 *  - GATED (perf-budgets.json `network`, shrink-only): the serial round-trip depth, the gzip
 *    bytes on the wire, the milliseconds until the heading shows and the last request is done.
 *  - Not the real thing: nothing here was measured from another continent.
 * `PERF_UPDATE=1` shrinks the budgets to the measured values + headroom (never raises one).
 */
import { appendFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';

import { expect, test, type Page, type Route } from '@playwright/test';

import { DISTANT, LinkModel, roundTripDepth, type Span } from '../scripts/network/model';
import { loadBudgets, saveBudgets, shrunk, type NetworkBudget } from '../scripts/perf-budgets';
import { mockViewer } from './auth-api';
import { mockApi } from './mock-api';

const ROUTES: { name: string; url: string }[] = [
  { name: 'Ideas', url: '/ideas' },
  { name: 'Test', url: '/test' },
  { name: 'Edges', url: '/edges' },
  { name: 'Regime', url: '/regime' },
  { name: 'Calendar', url: '/calendar' },
  { name: 'Explore', url: '/explore' },
  { name: 'Admin ingestion', url: '/admin/ingestion' },
];

interface Measured extends NetworkBudget {
  requests: number;
  api_gzip_bytes: number;
}
const results = new Map<string, Measured>();

type Fulfilled = NonNullable<Parameters<Route['fulfill']>[0]>;

const COMPRESSIBLE = /text|javascript|json|svg|xml/;

/** Holds every response back by the link model; returns what it saw once the page is done. */
async function distantLink(page: Page, origin: string) {
  const model = new LinkModel(DISTANT);
  const spans: Span[] = [];
  const t0 = performance.now();
  const files = new Map<string, Promise<Fulfilled>>();
  let staticBytes = 0;
  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url());
    const start = performance.now() - t0;
    if (url.origin === origin && !url.pathname.startsWith('/api/')) {
      // Playwright's routing turns the HTTP cache off: a file asked for twice (a preload, then
      // the page's own link) is one transfer in the browser, so the second waits for the first.
      let served = files.get(url.href);
      if (served === undefined) {
        served = (async (): Promise<Fulfilled> => {
          const fetched = await route.fetch();
          const body = await fetched.body();
          const type = fetched.headers()['content-type'] ?? '';
          // Playwright hands over and takes the decoded body: the link carries what the real
          // server would send (gzip for text), the page gets the plain body.
          const wire = COMPRESSIBLE.test(type) ? gzipSync(body, { level: 6 }) : body;
          const wait = model.delay(performance.now() - t0, wire.length);
          staticBytes += wire.length;
          spans.push({ start, end: start + wait, label: url.pathname });
          await new Promise((resolve) => setTimeout(resolve, wait));
          const kept = ['content-encoding', 'content-length', 'transfer-encoding'];
          return {
            status: fetched.status(),
            headers: {
              ...Object.fromEntries(
                Object.entries(fetched.headers()).filter(([name]) => !kept.includes(name)),
              ),
              'content-length': String(body.length),
            },
            body,
          };
        })();
        files.set(url.href, served);
      }
      await route.fulfill(await served);
      return;
    }
    if (url.pathname.startsWith('/api/')) {
      const wait = model.delay(performance.now() - t0, 0);
      const query = (route.request().postDataJSON() as { query?: string } | null)?.query;
      const operation = /(?:query|mutation)\s+(\w+)/.exec(query ?? '')?.[1] ?? '';
      spans.push({ start, end: start + wait, label: `${url.pathname} ${operation}` });
      await new Promise((resolve) => setTimeout(resolve, wait));
    }
    await route.fallback();
  });
  let apiBytes = 0;
  const bodies: Promise<void>[] = [];
  page.on('response', (response) => {
    if (!new URL(response.url()).pathname.startsWith('/api/')) return;
    bodies.push(
      response
        .body()
        .then((body) => {
          apiBytes += gzipSync(body, { level: 6 }).length;
        })
        .catch(() => undefined),
    );
  });
  return {
    t0,
    result: async () => {
      await Promise.all(bodies);
      return { spans, staticBytes, apiBytes };
    },
  };
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await mockViewer(page);
});

for (const route of ROUTES) {
  test(`${route.name} stays within its round-trip, byte and time budgets on a distant link`, async ({
    page,
    baseURL,
  }) => {
    test.setTimeout(120_000);
    const link = await distantLink(page, new URL(baseURL ?? '').origin);
    await page.goto(route.url, { waitUntil: 'commit' });
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible({ timeout: 60_000 });
    const readyAt = performance.now() - link.t0;
    await page.waitForLoadState('networkidle');
    const seen = await link.result();
    if (process.env['PERF_TRACE'] !== undefined) {
      for (const s of [...seen.spans].sort((a, b) => a.start - b.start)) {
        console.log(
          `${route.url} ${String(Math.round(s.start))} -> ${String(Math.round(s.end))} ${s.label ?? ''}`,
        );
      }
    }
    const last = Math.max(...seen.spans.map((s) => s.end));
    const measured: Measured = {
      round_trip_depth: roundTripDepth(seen.spans),
      wire_gzip_bytes: seen.staticBytes + seen.apiBytes,
      settled_ms: Math.round(Math.max(readyAt, last)),
      requests: seen.spans.length,
      api_gzip_bytes: seen.apiBytes,
    };
    results.set(route.url, measured);

    if (process.env['PERF_UPDATE'] !== undefined) return;
    const budget = loadBudgets().network?.[route.url];
    expect(
      budget,
      `no budget for ${route.url}: run \`PERF_UPDATE=1 npm run perf:network\``,
    ).toBeDefined();
    const b = budget as NetworkBudget;
    expect(measured.round_trip_depth, 'serial round trips over budget').toBeLessThanOrEqual(
      b.round_trip_depth,
    );
    expect(measured.wire_gzip_bytes, 'gzip bytes on the wire over budget').toBeLessThanOrEqual(
      b.wire_gzip_bytes,
    );
    expect(measured.settled_ms, 'time to a settled page over budget').toBeLessThanOrEqual(
      b.settled_ms,
    );
  });
}

test.afterAll(() => {
  const budgets = loadBudgets();
  const kb = (bytes: number): string => `${(bytes / 1000).toFixed(1)} kB`;
  const lines = [
    `| Route (${String(DISTANT.rttMs)} ms RTT, ${String(DISTANT.downMbit)} Mbit/s) | Round trips | Wire gzip (API part) | Requests | Settled |`,
    '|---|---|---|---|---|',
  ];
  for (const route of ROUTES) {
    const m = results.get(route.url);
    if (m === undefined) continue;
    const b = budgets.network?.[route.url];
    const of = (value: number, budget: number | undefined, show: (n: number) => string): string =>
      budget === undefined ? show(value) : `${show(value)} / ${show(budget)}`;
    lines.push(
      `| ${route.name} | ${of(m.round_trip_depth, b?.round_trip_depth, String)} | ${of(m.wire_gzip_bytes, b?.wire_gzip_bytes, kb)} (${kb(m.api_gzip_bytes)}) | ${String(m.requests)} | ${of(m.settled_ms, b?.settled_ms, (n) => `${(n / 1000).toFixed(1)} s`)} |`,
    );
  }
  const text = lines.join('\n');
  console.log(
    `\n${text}\n(value / budget; a link model, not a measurement from another continent)`,
  );
  const summary = process.env['GITHUB_STEP_SUMMARY'];
  if (summary !== undefined) appendFileSync(summary, `${text}\n\n`);

  if (process.env['PERF_UPDATE'] !== undefined) {
    budgets.network ??= {};
    for (const route of ROUTES) {
      const m = results.get(route.url);
      if (m === undefined) continue;
      const old = budgets.network[route.url];
      budgets.network[route.url] = {
        round_trip_depth: shrunk(old?.round_trip_depth, m.round_trip_depth, 1),
        wire_gzip_bytes: shrunk(old?.wire_gzip_bytes, Math.ceil(m.wire_gzip_bytes * 1.03)), // CI's API bodies differ a little
        settled_ms: shrunk(old?.settled_ms, Math.ceil(m.settled_ms * 1.3), 100), // 30 % for CI's load (it ran 2.9 s where a laptop ran 2.4 s)
      };
    }
    saveBudgets(budgets);
  }
});
