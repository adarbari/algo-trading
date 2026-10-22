// `make api-latency-views-capture`: the crawler's entry, started by `capture_views.py` (which has
// already refused the real store). Visits the views of benchmarks/api_latency_views.json against
// an API that serves a CLONE and a web server proxying to it (both given, never started here),
// and writes what each view sent back into the file after every view (resumable).
//
// One browser, one context, one page at a time; at most --max-views views per run.
import { readFileSync, renameSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { crawl, installGuard, pending, resolveUrl } from './view_crawler.mjs';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const { chromium } = createRequire(resolve(repo, 'apps/web/package.json'))('@playwright/test');

const args = Object.fromEntries(
  process.argv.slice(2).flatMap((a, i, all) => (a.startsWith('--') ? [[a.slice(2), all[i + 1]]] : [])),
);
const need = (k) => {
  if (!args[k]) throw new Error(`--${k} is required`);
  return args[k];
};
const apiUrl = need('api-url');
const webUrl = need('web-url').replace(/\/$/, '');
const file = resolve(need('views-file'));
const opts = {
  webUrl,
  maxViews: Number(args['max-views'] ?? 20),
  onlyRoute: args['only-route'] || undefined,
  viewTimeoutMs: Number(args['view-timeout'] ?? 60) * 1000,
  depth: Number(args.depth ?? 2),
  maxControls: Number(args['max-controls'] ?? 40),
  retry: args.retry === 'true',
  blocked: [],
};

const gql = async (query) => {
  const res = await fetch(`${apiUrl.replace(/\/$/, '')}/graphql`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  return (await res.json()).data ?? {};
};

/** Real ids from the clone: the first edge, screener and run, a ticker, the latest session. */
async function pickIds() {
  const picks = { instrument: 'AAPL' };
  const tries = {
    edge: async () => (await gql('{ edges { id } }')).edges?.[0]?.id,
    screener: async () => (await gql('{ screeners { id } }')).screeners?.[0]?.id,
    run: async () => (await gql('{ nightlyRuns(limit: 1) { runId } }')).nightlyRuns?.[0]?.runId,
    session: async () => (await gql('{ session { date } }')).session?.date,
  };
  for (const [kind, fn] of Object.entries(tries)) {
    try {
      const id = await fn();
      if (id) picks[kind] = id;
    } catch (e) {
      console.warn(`no ${kind} pick: ${e.message}`);
    }
  }
  return picks;
}

/** Ids for `link` params (the Guide's pages): the first anchor on the route's section page. */
async function scrapeLinks(doc, picks, context) {
  const page = await context.newPage();
  try {
    // only the views this run will visit (--max-views, --only-route), never the whole file
    const visiting = pending(doc, opts).slice(0, opts.maxViews).map((id) => doc.views[id]);
    for (const view of visiting) {
      for (const [param, kind] of Object.entries(view.params ?? {})) {
        const key = `param:${view.route}:${param}`;
        if (kind !== 'link' || picks[key] !== undefined) continue;
        const section = view.route.split('/:')[0];
        const pattern = new RegExp(
          `^${view.route.replace(/:splat/g, '(.+)').replace(/:(\\w+)/g, '([^/?#]+)')}$`,
        );
        await page.goto(`${webUrl}${section}`, { timeout: opts.viewTimeoutMs }).catch(() => {});
        await page.waitForLoadState('networkidle', { timeout: opts.viewTimeoutMs }).catch(() => {});
        const hrefs = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map((a) => a.getAttribute('href')));
        const hit = hrefs.map((h) => pattern.exec((h ?? '').split(/[?#]/)[0])).find(Boolean);
        const names = [...view.route.matchAll(/:(\w+)/g)].map((m) => m[1]);
        if (hit) names.forEach((n, i) => (picks[`param:${view.route}:${n}`] = decodeURIComponent(hit[i + 1])));
      }
    }
  } finally {
    await page.close();
  }
}

const save = (doc) => {
  const tmp = `${file}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(doc, null, 1)}\n`);
  renameSync(tmp, file); // atomic: a stopped run never leaves half a file
};

const doc = JSON.parse(readFileSync(file, 'utf8'));
const browser = await chromium.launch();
try {
  const context = await browser.newContext();
  await installGuard(context, webUrl, opts.blocked); // reads of the web origin only
  const picks = await pickIds();
  await scrapeLinks(doc, picks, context);
  console.log('picks', JSON.stringify(picks));
  const unresolved = Object.entries(doc.views).filter(([, v]) => !v.captured && resolveUrl(v, picks) === null);
  if (unresolved.length) console.log(`${unresolved.length} views have no real id and are skipped`);
  const done = await crawl(doc, picks, opts, () => context.newPage(), save, (m) => console.log(m));
  console.log(`visited ${done.visited} views, ${done.remaining} left in the queue`);
} finally {
  await browser.close();
}
