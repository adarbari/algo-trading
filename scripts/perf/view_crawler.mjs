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

// A control the crawler never clicks: its name starts with a verb that writes or runs something.
// The network guard below is the real backstop; this keeps the page from trying.
const DENY =
  /^\W*(save|delete|remove|finali[sz]e|copy|duplicate|run (now|again|screener|it)|evaluate|follow|unfollow|publish|submit|apply|create|reset|clear|discard|approve|reject|waive|retry|send|sign out|log ?out|accept|dismiss|pause|resume|add|new|start)\b/i;
export const denied = (name) => DENY.test(name);

/**
 * Whether a browser request may leave: only the web origin (Vite, which proxies to the clone's
 * API), only reads: GET / HEAD / OPTIONS, and POST /api/graphql when no document is a mutation.
 * Everything else (REST writes such as /regime/explain, /screens/*\/run, previews, saves) is
 * aborted and named in the view's note.
 */
export function decide(method, url, postData, webOrigin) {
  const u = new URL(url);
  if (u.origin !== webOrigin) return { allow: false, reason: `off-origin ${u.origin}` };
  if (['GET', 'HEAD', 'OPTIONS'].includes(method)) return { allow: true };
  if (method === 'POST' && u.pathname === GRAPHQL_PATH) {
    try {
      const body = JSON.parse(postData ?? '');
      const docs = (Array.isArray(body) ? body : [body]).map((q) => String(q.query ?? ''));
      if (!docs.some((d) => /\bmutation\b/.test(d))) return { allow: true };
      return { allow: false, reason: 'POST /graphql mutation' };
    } catch {
      return { allow: false, reason: 'POST /graphql unreadable body' };
    }
  }
  return { allow: false, reason: `${method} ${u.pathname}` };
}

/** Install the guard on a browser context; every refused request is pushed to ``blocked``. */
export async function installGuard(context, webUrl, blocked) {
  const origin = new URL(webUrl).origin;
  await context.route('**/*', (route) => {
    const req = route.request();
    const d = decide(req.method(), req.url(), req.postData(), origin);
    if (d.allow) return route.continue();
    blocked.push(d.reason);
    return route.abort('blockedbyclient');
  });
}

/** A route pattern: equal, a path prefix (`/edges` covers `/edges/:id`) or a `*` glob. */
export function routeMatches(route, pattern) {
  if (!pattern) return true;
  if (pattern.includes('*')) {
    const re = new RegExp(`^${pattern.split('*').map((p) => p.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*')}$`);
    return re.test(route);
  }
  return route === pattern || route.startsWith(`${pattern.replace(/\/$/, '')}/`);
}
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
/**
 * Runs in the page (self-contained): finds the controls ONE way for both discovery and clicking
 * (same selector, same label, same nth among the controls of that kind and label), so a
 * discovered control is the one that gets clicked. mode "discover" lists the tabs not selected,
 * the collapsed expanders and the unchecked radios; mode "click" clicks the nth one named so.
 */
export function inPage(arg) {
  const SEL = { tab: '[role="tab"]', expand: 'button[aria-expanded]', radio: '[role="radio"]' };
  const on = {
    tab: (el) => el.getAttribute('aria-selected') === 'true',
    expand: (el) => el.getAttribute('aria-expanded') === 'true',
    radio: (el) => el.getAttribute('aria-checked') === 'true',
  };
  const label = (el) => (el.getAttribute('aria-label') ?? el.textContent ?? '').trim().replace(/\s+/g, ' ');
  const seen = new Map();
  const found = [];
  for (const kind of Object.keys(SEL)) {
    for (const el of document.querySelectorAll(SEL[kind])) {
      const name = label(el);
      if (arg.mode === 'click') {
        if (kind !== arg.kind || !(name === arg.name || name.startsWith(`${arg.name} `))) continue;
        const n = seen.get('c') ?? 0;
        seen.set('c', n + 1);
        if (n === arg.nth) {
          el.click();
          return true;
        }
      } else if (name) {
        const key = `${kind}:${name}`;
        const nth = seen.get(key) ?? 0;
        seen.set(key, nth + 1);
        if (!on[kind](el)) found.push({ kind, name, nth });
      }
    }
  }
  return arg.mode === 'click' ? false : found;
}

/** Click one step of a view's path; false when the control is not on the page (or is denied). */
export async function applyClick(page, click) {
  if (denied(click.name)) return false;
  return page.evaluate(inPage, { mode: 'click', kind: click.kind, name: click.name, nth: click.nth ?? 0 });
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

/** The controls on the page now (see ``inPage``), the denied ones dropped. */
export async function discover(page) {
  const found = await page.evaluate(inPage, { mode: 'discover' });
  return found.filter((c) => !denied(c.name));
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
  const blockedFrom = opts.blocked?.length ?? 0;
  let status = 'ok';
  let note = '';
  let controls = [];
  const visit = async () => {
    await page.goto(`${opts.webUrl}${url}`, { timeout: opts.viewTimeoutMs });
    await settle(page, opts.viewTimeoutMs);
    for (const click of view.clicks ?? []) {
      state.trigger = `click:${click.kind}:${click.name}`;
      if (!(await applyClick(page, click))) {
        status = 'missing';
        note = `${click.kind} "${click.name}" is not on the page (or is a denied action)`;
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
  const blocked = [...new Set((opts.blocked ?? []).slice(blockedFrom))];
  if (blocked.length) note = `${note} blocked: ${blocked.slice(0, 8).join('; ')}`.trim();
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

/** The view ids this run would visit, in file order (not captured yet, or retried). */
export function pending(doc, opts) {
  return Object.entries(doc.views)
    .filter(
      ([, v]) =>
        (!v.captured || (opts.retry && RETRY.has(v.captured.status))) &&
        routeMatches(v.route, opts.onlyRoute),
    )
    .map(([id]) => id);
}

/**
 * Crawl the views file: queue = views not yet captured (resumable), at most `maxViews` this run,
 * `onlyRoute` restricts to a route pattern, `retry` revisits the views that did not finish. Discovered controls become child views, saved into
 * the file with the captured result. `save(doc)` runs after every view; `newPage()` gives a fresh
 * page of the one browser context and the page is closed after the view.
 */
export async function crawl(doc, picks, opts, newPage, save, log = () => {}) {
  const seen = new Set(Object.values(doc.views).map(signature));
  const queue = pending(doc, opts);
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
