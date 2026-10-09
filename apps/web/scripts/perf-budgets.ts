/**
 * The web performance budgets file (perf-budgets.json): its shape, loading, and the one rule that
 * changes it. Budgets only shrink: `shrunk` keeps the old budget unless the measured value plus
 * the 1 % headroom is lower, so a script never raises a budget (raising one is a visible edit of the
 * JSON in the PR). Shared by the bundle check and the Playwright request / DOM budgets.
 */
import { readFileSync, writeFileSync } from 'node:fs';

export interface RouteBudget {
  /** Gzip bytes of every script the route's first load transfers (entry, vendor, its chunks). */
  first_load_js_gzip_bytes: number;
  /** Requests the first load makes until the page is settled (document, scripts, fonts, API). */
  requests: number;
  /** Elements in the document once the page is settled. */
  dom_nodes: number;
}

export interface Budgets {
  bundle: {
    /** The entry chunk's own JS + CSS, gzip: what every first visit downloads before any route. */
    entry_gzip_bytes: number;
    /** The entry plus every chunk it imports statically (vendor included), gzip. */
    entry_closure_gzip_bytes: number;
    /** Manifest sources that must stay out of the entry's static closure (lazy-loaded libraries). */
    lazy_only: string[];
    /** Per lazy page (manifest source): the gzip bytes it adds beyond the entry's closure. */
    routes: Record<string, number>;
  };
  /** Per URL, as the Playwright budgets (e2e/perf.spec.ts) measure it on the phone project. */
  e2e: Record<string, RouteBudget>;
  /**
   * Why a budget was raised: budget path (`bundle.routes.<page>`, `e2e.<url>.requests`, ...) ->
   * "YYYY-MM-DD #PR what the owner asked for". Never read by the checks; kept by every update.
   */
  reasons?: Record<string, string>;
}

/** The budgets every route shares: they only ever go down, whatever the reason. */
export const SHARED_BUDGETS: readonly string[] = [
  'bundle.entry_gzip_bytes',
  'bundle.entry_closure_gzip_bytes',
];

/** Every numeric budget by path (`bundle.routes.<page>`, `e2e.<url>.dom_nodes`, ...). */
export function flatten(budgets: Budgets): Record<string, number> {
  const out: Record<string, number> = {
    'bundle.entry_gzip_bytes': budgets.bundle.entry_gzip_bytes,
    'bundle.entry_closure_gzip_bytes': budgets.bundle.entry_closure_gzip_bytes,
  };
  for (const [page, size] of Object.entries(budgets.bundle.routes)) {
    out[`bundle.routes.${page}`] = size;
  }
  for (const [url, b] of Object.entries(budgets.e2e)) {
    for (const key of ['first_load_js_gzip_bytes', 'requests', 'dom_nodes'] as const) {
      out[`e2e.${url}.${key}`] = b[key];
    }
  }
  return out;
}

const REASON = /^\d{4}-\d{2}-\d{2} #\d+ \S/;

/**
 * The budgets that rose against `base` without being allowed to: a shared budget never; a route's
 * own only with a reason in the same change (an entry in `reasons` that is new or different from
 * base's, shaped "YYYY-MM-DD #PR text"). Empty: nothing rose wrongly.
 */
export function unexplainedRises(base: Budgets, head: Budgets): string[] {
  const before = flatten(base);
  const out: string[] = [];
  for (const [path, value] of Object.entries(flatten(head))) {
    const old = before[path];
    if (old === undefined || value <= old) continue;
    if (SHARED_BUDGETS.includes(path)) {
      out.push(`${path} rose from ${String(old)} to ${String(value)}: shared budgets only go down`);
      continue;
    }
    const reason = head.reasons?.[path];
    if (reason === undefined || reason === base.reasons?.[path] || !REASON.test(reason)) {
      out.push(
        `${path} rose from ${String(old)} to ${String(value)} with no new reason ("YYYY-MM-DD #PR why") in perf-budgets.json reasons`,
      );
    }
  }
  return out;
}

/** The reasons of budgets a measured value is within 5 % of (or over): shown beside the table. */
export function nearBudgetNotes(measured: Record<string, number>, budgets: Budgets): string[] {
  const budget = flatten(budgets);
  return Object.entries(measured)
    .filter(([path, value]) => {
      const limit = budget[path];
      return (
        limit !== undefined && budgets.reasons?.[path] !== undefined && value * 100 >= limit * 95
      );
    })
    .map(([path]) => `${path} was raised: ${budgets.reasons?.[path] ?? ''}`);
}

export const BUDGETS_FILE = new URL('../perf-budgets.json', import.meta.url);

export function loadBudgets(file: URL = BUDGETS_FILE): Budgets {
  return JSON.parse(readFileSync(file, 'utf8')) as Budgets;
}

export function saveBudgets(budgets: Budgets, file: URL = BUDGETS_FILE): void {
  writeFileSync(file, `${JSON.stringify(budgets, null, 2)}\n`);
}

/**
 * The budget after seeing `measured`: measured + 1 % headroom (CI measures a few hundred bytes more
 * than a laptop: gzip and build variance), rounded UP to `step` (100 B for sizes, 1 for counts) and
 * at least `measured + 1`; never above the old budget, so it only shrinks. With no old budget
 * (a new page or route) the headroom value is its first budget.
 */
export function withHeadroom(measured: number, step = 100): number {
  const rounded = Math.ceil((measured * 101) / (100 * step)) * step; // integer maths: 1.01 is inexact
  return Math.max(rounded, measured + 1);
}

export function shrunk(old: number | undefined, measured: number, step = 100): number {
  const wanted = withHeadroom(measured, step);
  return old === undefined ? wanted : Math.min(old, wanted);
}
