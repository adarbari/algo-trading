// `make api-latency-capture`: what the web app sends to the API on load, per route.
//
// Starts its OWN API (free port, the real local store, ALGOTRADE_AUTH=off) and a Vite dev server
// proxying to it, opens every route in headless Chromium, waits until the page settles and
// records each GraphQL operation (name, variables, document) and REST GET the page fired.
// Writes benchmarks/api_latency_pages.json, the input `scripts/perf/api_latency.py` replays.
// Never touches an API already running (the launchd one on :8000).
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createServer } from 'node:net';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const web = resolve(repo, 'apps/web');
const { chromium } = createRequire(resolve(web, 'package.json'))('@playwright/test');
const python = process.env.ALGOTRADE_PY ?? resolve(repo, '.venv/bin/python');
const out = resolve(repo, 'benchmarks/api_latency_pages.json');

// Section paths of apps/web/src/app/workspaces/workspaces.ts plus the parameterised routes
// (real ids: a ticker the store holds, a screener the config ships).
const ROUTES = (
  process.env.CAPTURE_ROUTES ??
  [
    '/ideas', '/screeners', '/screeners/vrp_scanner', '/screeners/new', '/edges',
    '/explore', '/explore?sel=AAPL', '/regime', '/calendar',
    '/admin/ingestion', '/admin/llm-usage', '/admin/harness-runs', '/admin/screener-runs',
    '/admin/users', '/guide', '/guide/start', '/guide/glossary', '/guide/fields',
    '/guide/playbooks', '/guide/situations', '/guide/regime',
  ].join(',')
).split(',');

const freePort = () =>
  new Promise((ok) => {
    const s = createServer().listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => ok(port));
    });
  });
const waitFor = async (url, ms = 90000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`timeout waiting for ${url}`);
};

const apiPort = await freePort();
const webPort = await freePort();
const kids = [];
const run = (cmd, args, opts) => {
  const k = spawn(cmd, args, { stdio: 'ignore', ...opts });
  kids.push(k);
  return k;
};
try {
  run(python, ['-m', 'uvicorn', 'algotrade_api.app:app', '--host', '127.0.0.1', '--port', String(apiPort)], {
    cwd: repo,
    env: { ...process.env, ALGOTRADE_AUTH: 'off', ALGOTRADE_LLM: 'off', ALGOTRADE_IBKR_PORT: '1' },
  });
  run('npx', ['vite', '--host', '127.0.0.1', '--port', String(webPort)], {
    cwd: web,
    env: { ...process.env, API_PROXY_TARGET: `http://127.0.0.1:${apiPort}` },
  });
  await waitFor(`http://127.0.0.1:${apiPort}/health`);
  await waitFor(`http://127.0.0.1:${webPort}/`);
  const browser = await chromium.launch();
  const pages = {};
  for (const route of ROUTES) {
    const page = await (await browser.newContext()).newPage();
    const calls = [];
    page.on('request', (req) => {
      const u = new URL(req.url());
      if (u.hostname !== '127.0.0.1' || u.port !== String(webPort)) return;
      if (!u.pathname.startsWith('/api/')) return; // the web's apiBaseUrl: Vite proxies it to the API
      if (req.method() === 'POST' && u.pathname === '/api/graphql') {
        const b = req.postDataJSON();
        for (const q of Array.isArray(b) ? b : [b])
          calls.push({
            kind: 'graphql',
            op: q.operationName ?? /(?:query|mutation)\s+(\w+)/.exec(q.query)?.[1] ?? 'anonymous',
            variables: q.variables ?? {},
            query: q.query,
          });
      } else if (req.method() === 'GET') {
        calls.push({ kind: 'rest', method: 'GET', path: u.pathname.slice(4) + u.search });
      }
    });
    await page.goto(`http://127.0.0.1:${webPort}${route}`);
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(1500);
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
    pages[route] = calls;
    await page.context().close();
    console.log(route, calls.length, 'calls');
  }
  await browser.close();
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, `${JSON.stringify({ pages }, null, 1)}\n`);
  console.log('written', out);
} finally {
  for (const k of kids) k.kill('SIGTERM');
}
