import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

import { describe, expect, it } from 'vitest';

import { loadBudgets, nearBudgetNotes, unexplainedRises, type Budgets } from './perf-budgets';

const base: Budgets = {
  bundle: {
    entry_gzip_bytes: 30000,
    entry_closure_gzip_bytes: 200000,
    lazy_only: [],
    routes: { 'src/pages/a/index.ts': 10000 },
  },
  e2e: { '/a': { first_load_js_gzip_bytes: 1000, requests: 10, dom_nodes: 100 } },
};
const raised = (over: Partial<Budgets>): Budgets => ({
  ...base,
  bundle: { ...base.bundle, routes: { 'src/pages/a/index.ts': 12000 } },
  ...over,
});

describe('unexplainedRises', () => {
  it('accepts a file that only shrinks or stays', () => {
    expect(unexplainedRises(base, base)).toEqual([]);
  });

  it('refuses a route budget that rose without a reason', () => {
    expect(unexplainedRises(base, raised({}))).toHaveLength(1);
  });

  it('accepts a rise with a new, dated reason and refuses an old or malformed one', () => {
    const path = 'bundle.routes.src/pages/a/index.ts';
    const reason = '2026-10-09 #420 Screeners rows v2: sparkline';
    expect(unexplainedRises(base, raised({ reasons: { [path]: reason } }))).toEqual([]);
    expect(unexplainedRises(base, raised({ reasons: { [path]: 'because' } }))).toHaveLength(1);
    expect(
      unexplainedRises(
        { ...base, reasons: { [path]: reason } },
        raised({ reasons: { [path]: reason } }),
      ),
    ).toHaveLength(1);
  });

  it('never lets a shared budget rise, reason or not', () => {
    const head = { ...base, bundle: { ...base.bundle, entry_gzip_bytes: 31000 } };
    const reasons = { 'bundle.entry_gzip_bytes': '2026-10-09 #1 more' };
    expect(unexplainedRises(base, { ...head, reasons })[0]).toContain('only go down');
  });
});

describe('an owner waiver of a shared budget', () => {
  const head = { ...base, bundle: { ...base.bundle, entry_gzip_bytes: 31000 } };
  const path = 'bundle.entry_gzip_bytes';
  const waiver = { max: 31000, log: '2026-10-18 | A section | Why' };

  it('allows a rise up to its ceiling, once', () => {
    const waivers = { [path]: waiver };
    expect(unexplainedRises(base, { ...head, waivers })).toEqual([]);
    expect(unexplainedRises({ ...base, waivers }, { ...head, waivers })).toHaveLength(1);
  });

  it('allows nothing over its ceiling', () => {
    const waivers = { [path]: { ...waiver, max: 30500 } };
    expect(unexplainedRises(base, { ...head, waivers })[0]).toContain("over its waiver's ceiling");
  });

  it('a reworded waiver with the same ceiling grants nothing more', () => {
    const waivers = { [path]: { ...waiver, log: 'another entry' } };
    expect(
      unexplainedRises({ ...base, waivers: { [path]: waiver } }, { ...head, waivers }),
    ).toHaveLength(1);
  });
});

describe('every waiver in perf-budgets.json', () => {
  const log = readFileSync(resolve(process.cwd(), '../../docs/decisions/log.md'), 'utf8');
  const waivers =
    loadBudgets(pathToFileURL(resolve(process.cwd(), 'perf-budgets.json'))).waivers ?? {};

  it.each(Object.entries(waivers))(
    '%s has an owner-final entry in the decision log',
    (_path, w) => {
      const start = log.indexOf(`## ${w.log}\n`);
      expect(start, `no "## ${w.log}" entry in docs/decisions/log.md`).toBeGreaterThanOrEqual(0);
      const next = log.indexOf('\n## ', start + 1);
      const entry = log.slice(start, next < 0 ? undefined : next);
      expect(entry).toContain('- decided by: owner\n');
      expect(entry).toContain('- status: final\n');
    },
  );
});

describe('nearBudgetNotes', () => {
  it('prints the reason of a raised budget that is within 5 % of its limit', () => {
    const budgets = raised({ reasons: { 'e2e./a.requests': '2026-10-09 #420 why' } });
    expect(nearBudgetNotes({ 'e2e./a.requests': 10 }, budgets)).toEqual([
      'e2e./a.requests was raised: 2026-10-09 #420 why',
    ]);
    expect(nearBudgetNotes({ 'e2e./a.requests': 5 }, budgets)).toEqual([]);
  });
});
