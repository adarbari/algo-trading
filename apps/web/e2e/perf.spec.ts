/**
 * Performance budgets on the phone (iPhone 13 device, CPU throttled 4x; playwright.perf.config.ts),
 * against the production build with the API mocked as in the other specs. For each main route the
 * first load is measured and two kinds of numbers come out:
 *  - GATED, deterministic counts, budgets in perf-budgets.json (`e2e`): gzip bytes of the scripts
 *    transferred, requests made, DOM nodes once settled. Over a budget fails the run.
 *  - REPORTED, never gated: LCP and total blocking time (long tasks after first paint). They move
 *    with the shared runner's load, so they go to the job summary only (docs/ci.md "Web performance").
 * `PERF_UPDATE=1` shrinks the budgets to the measured counts + 5 % (never raises one).
 */
import { appendFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';

import { expect, test, type Locator, type Page, type Response } from '@playwright/test';

import {
  loadBudgets,
  nearBudgetNotes,
  saveBudgets,
  shrunk,
  type RouteBudget,
} from '../scripts/perf-budgets';
import { settled } from './a11y';
import { mockViewer } from './auth-api';
import { mockApi } from './mock-api';

/** `ready`: what shows the route has rendered (default: its heading; a ticker opens a sheet). */
const ROUTES: { name: string; url: string; ready?: (page: Page) => Locator }[] = [
  { name: 'Ideas', url: '/ideas' },
  { name: 'Screeners', url: '/screeners' },
  {
    name: 'Explore with a ticker (chart tab)',
    url: '/explore?focus=AAPL&tab=chart',
    ready: (page) => page.getByRole('button', { name: 'Zoom in' }),
  },
  {
    name: 'Explore with a ticker (features tab)',
    url: '/explore?focus=AAPL&tab=features',
    ready: (page) => page.getByRole('grid', { name: 'AAPL features' }),
  },
  { name: 'Regime', url: '/regime' },
  { name: 'Screener results', url: '/screeners/vrp_scanner' },
  { name: 'Admin ingestion', url: '/admin/ingestion' },
];
const CPU_THROTTLE = 4;

interface Measured extends RouteBudget {
  lcp_ms: number | null;
  tbt_ms: number;
}
const results = new Map<string, Measured>();

/** Observers installed before the page's own scripts run (LCP, first paint, long tasks). */
async function observeTimings(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as {
      __perf: { lcp: number | null; fcp: number; tasks: [number, number][] };
    };
    w.__perf = { lcp: null, fcp: Infinity, tasks: [] };
    const watch = (type: string, onEntry: (e: PerformanceEntry) => void): void => {
      new PerformanceObserver((list) => {
        list.getEntries().forEach(onEntry);
      }).observe({
        type,
        buffered: true,
      });
    };
    watch('largest-contentful-paint', (e) => {
      w.__perf.lcp = e.startTime;
    });
    watch('paint', (e) => {
      if (e.name === 'first-contentful-paint') w.__perf.fcp = e.startTime;
    });
    watch('longtask', (e) => {
      w.__perf.tasks.push([e.startTime, e.duration]);
    });
  });
}

/** Gzip bytes of every script the page loads, whatever the preview server's own encoding. */
function trackScripts(page: Page): { done: () => Promise<number>; requests: () => number } {
  const bodies: Promise<number>[] = [];
  // Routing turns the browser's HTTP cache off, so a file the page preloads and then uses (the
  // route-preload plugin) is asked for twice here and once in a real browser: a GET counts once.
  const seen = new Set<string>();
  let requests = 0;
  page.on('request', (request) => {
    if (request.method() === 'GET') {
      if (seen.has(request.url())) return;
      seen.add(request.url());
    }
    requests += 1;
  });
  page.on('response', (response: Response) => {
    if (response.request().resourceType() !== 'script') return;
    bodies.push(
      response
        .body()
        .then((body) => gzipSync(body, { level: 9 }).length)
        .catch(() => 0),
    );
  });
  return {
    done: async () => (await Promise.all(bodies)).reduce((a, b) => a + b, 0),
    requests: () => requests,
  };
}

/**
 * The nodes of the rendered page (`<body>`), once the count has not changed for `QUIET_MS`.
 * `<head>` is not counted: the route-preload plugin adds `<link rel=modulepreload>` elements as
 * chunks preload, three to four of them on some runs and not on others (Screeners read 238-245
 * for the same page; the requests budget already covers the preloads). A fixed pause also
 * counted whatever had rendered by then, so the wait is for a quiet DOM. Fails when it never settles.
 */
const QUIET_MS = 2000;
const SETTLE_TIMEOUT_MS = 30_000;
async function settledNodeCount(page: Page): Promise<number> {
  return page.evaluate(
    async ({ quiet, timeout }) => {
      const count = (): number => document.body.querySelectorAll('*').length;
      const start = performance.now();
      let last = count();
      let since = performance.now();
      while (performance.now() - start < timeout) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        const now = count();
        if (now !== last) {
          last = now;
          since = performance.now();
        } else if (performance.now() - since >= quiet) return now;
      }
      throw new Error(`the DOM node count never settled (last ${String(last)})`);
    },
    { quiet: QUIET_MS, timeout: SETTLE_TIMEOUT_MS },
  );
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await mockViewer(page);
});

for (const route of ROUTES) {
  test(`${route.name} stays within its request, script and DOM budgets`, async ({ page }) => {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: CPU_THROTTLE });
    await observeTimings(page);
    const tracker = trackScripts(page);

    await page.goto(route.url);
    await expect(
      (route.ready ?? ((p: Page) => p.getByRole('heading', { level: 1 }).first()))(page),
    ).toBeVisible();
    await page.waitForLoadState('networkidle');
    await settled(page);
    const nodes = await settledNodeCount(page); // a lazy chunk or a help term can still be on its way

    const dom = await page.evaluate(() => {
      const perf = (
        window as unknown as {
          __perf: { lcp: number | null; fcp: number; tasks: [number, number][] };
        }
      ).__perf;
      const blocking = perf.tasks
        .filter(([start]) => start >= perf.fcp)
        .reduce((sum, [, duration]) => sum + Math.max(0, duration - 50), 0);
      return {
        lcp: perf.lcp,
        tbt: blocking,
      };
    });
    const measured: Measured = {
      first_load_js_gzip_bytes: await tracker.done(),
      requests: tracker.requests(),
      dom_nodes: nodes,
      lcp_ms: dom.lcp === null ? null : Math.round(dom.lcp),
      tbt_ms: Math.round(dom.tbt),
    };
    results.set(route.url, measured);

    if (process.env['PERF_UPDATE'] !== undefined) return;
    const budget = loadBudgets().e2e[route.url];
    expect(
      budget,
      `no budget for ${route.url}: run \`PERF_UPDATE=1 npm run perf:e2e\``,
    ).toBeDefined();
    const b = budget as RouteBudget;
    expect(
      measured.first_load_js_gzip_bytes,
      'script bytes (gzip) over budget',
    ).toBeLessThanOrEqual(b.first_load_js_gzip_bytes);
    expect(measured.requests, 'requests over budget').toBeLessThanOrEqual(b.requests);
    expect(measured.dom_nodes, 'DOM nodes over budget').toBeLessThanOrEqual(b.dom_nodes);
  });
}

test.afterAll(() => {
  const budgets = loadBudgets();
  const kb = (bytes: number): string => `${(bytes / 1000).toFixed(1)} kB`;
  const lines = [
    `| Route (phone, CPU ${String(CPU_THROTTLE)}x) | Script gzip | Requests | DOM nodes | LCP (report only) | TBT (report only) |`,
    '|---|---|---|---|---|---|',
  ];
  for (const route of ROUTES) {
    const m = results.get(route.url);
    if (m === undefined) continue;
    const b = budgets.e2e[route.url];
    const of = (value: number, budget: number | undefined, show: (n: number) => string): string =>
      budget === undefined ? show(value) : `${show(value)} / ${show(budget)}`;
    lines.push(
      `| ${route.name} | ${of(m.first_load_js_gzip_bytes, b?.first_load_js_gzip_bytes, kb)} | ${of(m.requests, b?.requests, String)} | ${of(m.dom_nodes, b?.dom_nodes, String)} | ${m.lcp_ms === null ? 'n/a' : `${String(m.lcp_ms)} ms`} | ${String(m.tbt_ms)} ms |`,
    );
  }
  const text = lines.join('\n');
  console.log(
    `\n${text}\n(value / budget; LCP and TBT are noise on shared runners and never fail)`,
  );
  const measuredByPath: Record<string, number> = {};
  for (const [url, m] of results) {
    measuredByPath[`e2e.${url}.first_load_js_gzip_bytes`] = m.first_load_js_gzip_bytes;
    measuredByPath[`e2e.${url}.requests`] = m.requests;
    measuredByPath[`e2e.${url}.dom_nodes`] = m.dom_nodes;
  }
  for (const note of nearBudgetNotes(measuredByPath, budgets)) console.log(note);
  const summary = process.env['GITHUB_STEP_SUMMARY'];
  if (summary !== undefined) appendFileSync(summary, `${text}\n\n`);

  if (process.env['PERF_UPDATE'] !== undefined) {
    for (const route of ROUTES) {
      const m = results.get(route.url);
      if (m === undefined) continue;
      const old = budgets.e2e[route.url];
      budgets.e2e[route.url] = {
        first_load_js_gzip_bytes: shrunk(old?.first_load_js_gzip_bytes, m.first_load_js_gzip_bytes),
        requests: shrunk(old?.requests, m.requests, 1),
        dom_nodes: shrunk(old?.dom_nodes, m.dom_nodes, 1),
      };
    }
    saveBudgets(budgets);
  }
});
