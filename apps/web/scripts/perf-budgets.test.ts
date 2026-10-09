import { describe, expect, it } from 'vitest';

import { nearBudgetNotes, unexplainedRises, type Budgets } from './perf-budgets';

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

describe('nearBudgetNotes', () => {
  it('prints the reason of a raised budget that is within 5 % of its limit', () => {
    const budgets = raised({ reasons: { 'e2e./a.requests': '2026-10-09 #420 why' } });
    expect(nearBudgetNotes({ 'e2e./a.requests': 10 }, budgets)).toEqual([
      'e2e./a.requests was raised: 2026-10-09 #420 why',
    ]);
    expect(nearBudgetNotes({ 'e2e./a.requests': 5 }, budgets)).toEqual([]);
  });
});
