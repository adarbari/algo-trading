/**
 * The web performance budgets file (perf-budgets.json): its shape, loading, and the one rule that
 * changes it. Budgets only shrink: `shrunk` keeps the old budget unless the measured value plus
 * the headroom is lower, so a script never raises a budget (raising one is a visible edit of the
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
}

export const BUDGETS_FILE = new URL('../perf-budgets.json', import.meta.url);

export function loadBudgets(file: URL = BUDGETS_FILE): Budgets {
  return JSON.parse(readFileSync(file, 'utf8')) as Budgets;
}

export function saveBudgets(budgets: Budgets, file: URL = BUDGETS_FILE): void {
  writeFileSync(file, `${JSON.stringify(budgets, null, 2)}\n`);
}

/**
 * The budget after seeing `measured`: the old one, or measured + 10 % (rounded up to `step`, 100 B
 * for sizes, 1 for counts) when that is lower, or when there is none.
 */
export function shrunk(old: number | undefined, measured: number, step = 100): number {
  const wanted = Math.ceil((measured * 11) / (10 * step)) * step; // integer maths: 12 000 * 1.1 is not exact;
  return old === undefined ? wanted : Math.min(old, wanted);
}
