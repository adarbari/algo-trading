// The crawler core of `capture_views.py`: visits the VIEWS of benchmarks/api_latency_views.json
// (a route, its search values and the clicks that reach a sub-view) in one browser context and
// records every GraphQL request each view sends (operation, variables, document, trigger, bytes).
//
// Pure of any browser: it takes a Playwright-shaped `page` (goto, on, waitForLoadState,
// waitForTimeout, getByRole, evaluate, close), so tests drive it with a fake. It never starts a
// server and never reads a store: the caller (`capture_views.py`) has already refused a real
// store.

export const GRAPHQL_PATH = '/api/graphql';
const SETTLE_MS = 800;
const SCROLL_STEPS = 12;

/** `{edge}` placeholders of a view's search / route params -> real ids; null when one is missing. */
export function resolveUrl(view, picks) {
  const fill = (text) => {
    let missing = false;
    const out = text.replace(/\{(\w+)\}/g, (_, kind) => {
      if (picks[kind] === undefined) missing = true;
      return String(picks[kind] ?? '');
    });
    return missing ? null : out;
  };
  let path = view.route;
  for (const [param, kind] of Object.entries(view.params ?? {})) {
    const id = picks[`param:${view.route}:${param}`] ?? picks[kind];
    if (id === undefined) return null;
    path = path.replace(`:${param}`, encodeURIComponent(String(id)));
  }
  const search = Object.entries(view.search ?? {});
  if (!search.length) return path;
  const query = search.map(([k, v]) => {
    const value = fill(String(v));
    return value === null ? null : `${k}=${encodeURIComponent(value)}`;
  });
  return query.includes(null) ? null : `${path}?${query.join('&')}`;
}

/** The signature of a view's interaction path, group-free (a discovered tab matches a static one). */
export function signature(view) {
  const search = Object.entries(view.search ?? {}).sort().map(([k, v]) => `${k}=${v}`).join('&');
  const clicks = (view.clicks ?? []).map((c) => `${c.kind}:${c.name}:${c.nth ?? 0}`).join('>');
  return `${view.route}?${search}|${clicks}`;
}

export function viewId(view) {
  const search = Object.entries(view.search ?? {}).sort().map(([k, v]) => `${k}=${v}`).join('&');
  const clicks = (view.clicks ?? []).map((c) => [c.kind, c.group, c.name].filter(Boolean).join(':'));
  return [view.route + (search ? `?${search}` : ''), ...clicks].join(' > ');
}

/** Records the GraphQL requests of a page. `state.trigger` labels the phase they belong to. */
export function record(page, state) {
  const pending = new Map();
  page.on('request', (req) => {
    const u = new URL(req.url());
    if (req.method() !== 'POST' || u.pathname !== GRAPHQL_PATH) return;
    let body;
    try {
      body = req.postDataJSON();
    } catch {
      return;
    }
    const entries = (Array.isArray(body) ? body : [body]).map((q) => ({
      op: q.operationName ?? /(?:query|mutation)\s+(\w+)/.exec(q.query ?? '')?.[1] ?? 'anonymous',
      variables: q.variables ?? {},
      query: q.query ?? '',
      trigger: state.trigger,
      bytes: 0,
    }));
    pending.set(req, entries);
    state.entries.push(...entries);
  });
  page.on('response', async (resp) => {
    const entries = pending.get(resp.request());
    if (!entries) return;
    let size = 0;
    try {
      size = (await resp.body()).length;
    } catch {
      /* a body that is gone: keep 0 */
    }
    for (const e of entries) e.bytes = Math.round(size / entries.length);
  });
}

/** The recorded entries folded to one row per (operation, variables, trigger) with a count. */
export function fold(entries) {
  const rows = new Map();
  for (const e of entries) {
    const key = `${e.op}|${JSON.stringify(e.variables)}|${e.trigger}`;
    const row = rows.get(key);
    if (row) row.count += 1;
    else rows.set(key, { ...e, count: 1 });
  }
  return [...rows.values()];
}

const settle = async (page, ms) => {
  await page.waitForLoadState('networkidle', { timeout: ms }).catch(() => {});
  await page.waitForTimeout(SETTLE_MS);
  await page.waitForLoadState('networkidle', { timeout: ms }).catch(() => {});
};

const RETRY = new Set(['skipped', 'timeout', 'error', 'missing']);
const ROLE = { tab: 'tab', expand: 'button', radio: 'radio' };

/** Click one step of a view's path; false when the control is not on the page. */
export async function applyClick(page, click, ms) {
  const loc = page.getByRole(ROLE[click.kind] ?? 'button', { name: click.name, exact: true });
  if ((await loc.count()) <= (click.nth ?? 0)) return false;
  await loc.nth(click.nth ?? 0).click({ timeout: ms });
  return true;
}

/** Scroll top to bottom in steps so lazy sections (intersection observers) load. */
export async function scrollThrough(page) {
  for (let i = 1; i <= SCROLL_STEPS; i += 1) {
    await page.evaluate(
      ([step, steps]) =>
        window.scrollTo(0, (document.documentElement.scrollHeight * step) / steps),
      [i, SCROLL_STEPS],
    );
    await page.waitForTimeout(150);
  }
}

/** The controls on the page now: tabs not selected, collapsed expanders, unchecked radios. */
export async function discover(page) {
  return page.evaluate(() => {
    const name = (el) => (el.getAttribute('aria-label') ?? el.textContent ?? '').trim().replace(/\s+/g, ' ');
    const count = new Map();
    const pick = (selector, kind) =>
      [...document.querySelectorAll(selector)].flatMap((el) => {
        const n = name(el);
        const nth = count.get(`${kind}:${n}`) ?? 0;
        count.set(`${kind}:${n}`, nth + 1);
        return n ? [{ kind, name: n, nth }] : [];
      });
    return [
      ...pick('[role="tab"]:not([aria-selected="true"])', 'tab'),
      ...pick('button[aria-expanded="false"]', 'expand'),
      ...pick('[role="radio"]:not([aria-checked="true"])', 'radio'),
    ];
  });
}

const withTimeout = (promise, ms) =>
  new Promise((ok) => {
    const t = setTimeout(() => ok('timeout'), ms);
    promise.then((v) => {
      clearTimeout(t);
      ok(v);
    });
  });

/** Visit one view; returns {status, note, requests, controls}. Never throws. */
export async function crawlView(page, view, picks, opts) {
  const state = { trigger: 'load', entries: [] };
  const url = resolveUrl(view, picks);
  if (url === null) return { status: 'skipped', note: 'no real id to fill a placeholder', requests: [], controls: [] };
  record(page, state);
  let status = 'ok';
  let note = '';
  let controls = [];
  const visit = async () => {
    await page.goto(`${opts.webUrl}${url}`, { timeout: opts.viewTimeoutMs });
    await settle(page, opts.viewTimeoutMs);
    for (const click of view.clicks ?? []) {
      state.trigger = `click:${click.kind}:${click.name}`;
      if (!(await applyClick(page, click, 5000))) {
        status = 'missing';
        note = `${click.kind} "${click.name}" is not on the page`;
        return;
      }
      await settle(page, opts.viewTimeoutMs);
    }
    state.trigger = 'scroll';
    await scrollThrough(page);
    await settle(page, opts.viewTimeoutMs);
    if ((view.clicks ?? []).length < opts.depth) controls = (await discover(page)).slice(0, opts.maxControls);
  };
  const done = await withTimeout(visit().catch((e) => ({ error: String(e?.message ?? e) })), opts.viewTimeoutMs);
  if (done === 'timeout') {
    status = 'timeout';
    note = `over ${opts.viewTimeoutMs / 1000} s`;
  } else if (done?.error) {
    status = 'error';
    note = done.error.slice(0, 200);
  }
  return { status, note, requests: fold(state.entries), controls };
}

/** A discovered control as a child view of ``parent`` (the same route, one more click). */
export function childView(parent, control) {
  return {
    route: parent.route,
    search: parent.search,
    clicks: [...(parent.clicks ?? []), control],
    params: parent.params,
    ops: [],
    uncertain: [],
    interaction: [],
    source: 'discovered',
    parent: viewId(parent),
  };
}

/**
 * Crawl the views file: queue = views not yet captured (resumable), at most `maxViews` this run,
 * `onlyRoute` restricts to a route pattern, `retry` revisits the views that did not finish. Discovered controls become child views, saved into
 * the file with the captured result. `save(doc)` runs after every view; `newPage()` gives a fresh
 * page of the one browser context and the page is closed after the view.
 */
export async function crawl(doc, picks, opts, newPage, save, log = () => {}) {
  const seen = new Set(Object.values(doc.views).map(signature));
  const queue = Object.entries(doc.views)
    .filter(
      ([, v]) =>
        (!v.captured || (opts.retry && RETRY.has(v.captured.status))) &&
        (!opts.onlyRoute || v.route === opts.onlyRoute),
    )
    .map(([id]) => id);
  let visited = 0;
  while (queue.length && visited < opts.maxViews) {
    const id = queue.shift();
    const view = doc.views[id];
    const page = await newPage();
    let result;
    try {
      result = await crawlView(page, view, picks, opts);
    } finally {
      await page.close().catch(() => {});
    }
    const { controls, ...captured } = result;
    view.captured = { ...captured, at: new Date().toISOString() };
    visited += 1;
    log(`${id}: ${captured.status}, ${captured.requests.length} request rows`);
    for (const control of controls) {
      const child = childView(view, control);
      if (seen.has(signature(child))) continue;
      seen.add(signature(child));
      const cid = viewId(child);
      doc.views[cid] = child;
      queue.push(cid);
    }
    save(doc);
  }
  return { visited, remaining: queue.length };
}
