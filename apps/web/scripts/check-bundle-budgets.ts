/**
 * Bundle budgets over the production build (`dist/.vite/manifest.json`, `build.manifest` in
 * vite.config.ts): fails when the entry chunk grows past its budget, when a page's lazy chunks
 * grow past theirs, or when a lazy-loaded library (the chart engine) leaks into the entry's static
 * imports. Sizes are gzip bytes of the emitted files, so the check is deterministic (no timing).
 * `tsx scripts/check-bundle-budgets.ts` checks; `... update` shrinks the budgets to the current
 * sizes + 1 % (never raises one; a new page gets its first budget). Prints a size table, also
 * into the GitHub job summary. Budgets: perf-budgets.json (scripts/perf-budgets.ts).
 */
import { appendFileSync, existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

import { execFileSync } from 'node:child_process';

import {
  loadBudgets,
  nearBudgetNotes,
  saveBudgets,
  shrunk,
  unexplainedRises,
  type Budgets,
} from './perf-budgets';

export interface ManifestChunk {
  file: string;
  src?: string;
  isEntry?: boolean;
  isDynamicEntry?: boolean;
  imports?: string[];
  css?: string[];
}
export type Manifest = Record<string, ManifestChunk>;

export interface Sizes {
  entry: number;
  entryClosure: number;
  /** Page (manifest source of a dynamic entry) -> gzip bytes beyond the entry's closure. */
  routes: Record<string, number>;
  /** Manifest sources of the lazy-only libraries found in the entry's static closure. */
  leaked: string[];
}

/** The manifest keys reachable from `key` through static imports (itself included). */
export function staticClosure(manifest: Manifest, key: string): Set<string> {
  const seen = new Set<string>();
  const visit = (k: string): void => {
    if (seen.has(k) || manifest[k] === undefined) return;
    seen.add(k);
    for (const next of manifest[k].imports ?? []) visit(next);
  };
  visit(key);
  return seen;
}

/** Every file (JS and CSS) a set of chunks emits. */
function filesOf(manifest: Manifest, keys: Iterable<string>): Set<string> {
  const files = new Set<string>();
  for (const key of keys) {
    const chunk = manifest[key];
    if (chunk === undefined) continue;
    files.add(chunk.file);
    for (const css of chunk.css ?? []) files.add(css);
  }
  return files;
}

export function entryKey(manifest: Manifest): string {
  const keys = Object.keys(manifest).filter((k) => manifest[k]?.isEntry === true);
  if (keys.length !== 1) throw new Error(`expected one entry chunk, found ${String(keys.length)}`);
  return keys[0] as string;
}

/** The sizes the budgets bound; `gzipSize(file)` is the gzip bytes of an emitted file. */
export function measure(
  manifest: Manifest,
  gzipSize: (file: string) => number,
  lazyOnly: readonly string[],
): Sizes {
  const entry = entryKey(manifest);
  const closure = staticClosure(manifest, entry);
  const total = (files: Iterable<string>): number =>
    [...files].reduce((sum, f) => sum + gzipSize(f), 0);
  const closureFiles = filesOf(manifest, closure);
  const own = manifest[entry] as ManifestChunk;
  const routes: Record<string, number> = {};
  for (const [key, chunk] of Object.entries(manifest)) {
    if (chunk.isDynamicEntry !== true || !key.startsWith('src/pages/')) continue;
    const extra = [...filesOf(manifest, staticClosure(manifest, key))].filter(
      (f) => !closureFiles.has(f),
    );
    routes[key] = total(extra);
  }
  return {
    entry: total([own.file, ...(own.css ?? [])]),
    entryClosure: total(closureFiles),
    routes,
    leaked: lazyOnly.filter((src) => closure.has(src)),
  };
}

/** What is over budget, as one sentence each; empty when the build is within every budget. */
export function violations(sizes: Sizes, budgets: Budgets['bundle']): string[] {
  const out: string[] = [];
  const over = (what: string, size: number, budget: number | undefined): void => {
    if (budget === undefined) {
      out.push(`${what}: no budget (run \`npm run perf:bundle -- update\` to set its first one)`);
    } else if (size > budget) {
      out.push(`${what}: ${String(size)} B gzip is over its budget of ${String(budget)} B`);
    }
  };
  over('entry chunk (JS + CSS)', sizes.entry, budgets.entry_gzip_bytes);
  over(
    'entry static imports (every first visit)',
    sizes.entryClosure,
    budgets.entry_closure_gzip_bytes,
  );
  for (const [page, size] of Object.entries(sizes.routes)) over(page, size, budgets.routes[page]);
  for (const src of sizes.leaked) {
    out.push(`${src} is in the entry's static imports: it must stay lazy (a dynamic import)`);
  }
  return out;
}

/** The budgets after an update: shrink-only, new pages added, pages that no longer exist dropped. */
export function updated(sizes: Sizes, budgets: Budgets): Budgets {
  const routes: Record<string, number> = {};
  for (const [page, size] of Object.entries(sizes.routes)) {
    routes[page] = shrunk(budgets.bundle.routes[page], size);
  }
  return {
    ...budgets,
    bundle: {
      ...budgets.bundle,
      entry_gzip_bytes: shrunk(budgets.bundle.entry_gzip_bytes, sizes.entry),
      entry_closure_gzip_bytes: shrunk(budgets.bundle.entry_closure_gzip_bytes, sizes.entryClosure),
      routes,
    },
  };
}

const kb = (bytes: number): string => `${(bytes / 1000).toFixed(1)} kB`;

/** The size table (Markdown, so the job summary renders it and the terminal reads it). */
export function table(sizes: Sizes, budgets: Budgets['bundle']): string {
  const row = (what: string, size: number, budget: number | undefined): string =>
    `| ${what} | ${kb(size)} | ${budget === undefined ? 'none' : kb(budget)} | ${
      budget === undefined || size > budget ? 'OVER' : 'ok'
    } |`;
  return [
    '| Bundle (gzip) | Size | Budget | |',
    '|---|---|---|---|',
    row('entry chunk (JS + CSS)', sizes.entry, budgets.entry_gzip_bytes),
    row(
      'entry + static imports (every first visit)',
      sizes.entryClosure,
      budgets.entry_closure_gzip_bytes,
    ),
    ...Object.entries(sizes.routes).map(([page, size]) => row(page, size, budgets.routes[page])),
  ].join('\n');
}

/**
 * Budgets raised against the base branch's file without a reason (see `unexplainedRises`). The base
 * is `origin/main` (BUDGETS_BASE_REF); where git or that ref is not there (a shallow CI checkout)
 * the comparison is skipped and review of the JSON is the check.
 */
function risesAgainstBase(head: Budgets): string[] {
  const ref = process.env['BUDGETS_BASE_REF'] ?? 'origin/main';
  try {
    const raw = execFileSync('git', ['show', `${ref}:apps/web/perf-budgets.json`], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    return unexplainedRises(JSON.parse(raw) as Budgets, head);
  } catch {
    console.log(
      `budget rises: ${ref} not available, skipped (a reviewer checks perf-budgets.json)`,
    );
    return [];
  }
}

const DIST = new URL('../dist/', import.meta.url);

function main(): number {
  const manifestFile = new URL('.vite/manifest.json', DIST);
  if (!existsSync(manifestFile)) {
    console.error(
      'dist/.vite/manifest.json is missing: run `npx vite build` first (make web-perf)',
    );
    return 1;
  }
  const manifest = JSON.parse(readFileSync(manifestFile, 'utf8')) as Manifest;
  const budgets = loadBudgets();
  const gzipSize = (file: string): number =>
    gzipSync(readFileSync(new URL(file, DIST)), { level: 9 }).length;
  const sizes = measure(manifest, gzipSize, budgets.bundle.lazy_only);
  const text = table(sizes, budgets.bundle);
  console.log(text);
  const summary = process.env['GITHUB_STEP_SUMMARY'];
  if (summary !== undefined) appendFileSync(summary, `${text}\n\n`);
  if (process.argv[2] === 'update') {
    saveBudgets(updated(sizes, budgets));
    console.log('perf-budgets.json: bundle budgets shrunk to the current sizes + 1 %');
    return 0;
  }
  const notes = nearBudgetNotes(
    {
      'bundle.entry_gzip_bytes': sizes.entry,
      'bundle.entry_closure_gzip_bytes': sizes.entryClosure,
      ...Object.fromEntries(
        Object.entries(sizes.routes).map(([page, size]) => [`bundle.routes.${page}`, size]),
      ),
    },
    budgets,
  );
  for (const note of notes) console.log(note);
  const problems = [...violations(sizes, budgets.bundle), ...risesAgainstBase(budgets)];
  for (const problem of problems) console.error(`FAIL ${problem}`);
  return problems.length === 0 ? 0 : 1;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) process.exitCode = main();
