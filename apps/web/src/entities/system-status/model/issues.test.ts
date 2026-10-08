import { describe, expect, it } from 'vitest';

import type { NightlyRun } from '@/entities/run';

import { systemIssues, type ScreenerStates } from './issues';

const run = (over: Partial<NightlyRun>): NightlyRun => ({
  runId: 'r1',
  session: '2026-10-08',
  status: 'FAILED',
  startedAt: '2026-10-08T06:00:00Z',
  finishedAt: null,
  durationS: null,
  problems: ['steps not complete: ibkr-iv'],
  steps: [
    { name: 'chains', status: 'SUCCEEDED', durationS: 1, reason: null, error: null },
    { name: 'ibkr-iv', status: 'FAILED', durationS: 1, reason: null, error: 'x' },
  ],
  ...over,
});

const screens = (missing: string[], total = 5): ScreenerStates => ({
  session: '2026-10-08',
  screeners: Array.from({ length: total }, (_, i) => ({
    screener: { id: `s${i}`, name: `Screener ${i}` },
    notRun: missing.includes(`s${i}`) ? { kindText: 'Not run for this session' } : null,
  })),
});

describe('systemIssues', () => {
  it('is empty when nothing is wrong or nothing has loaded', () => {
    expect(systemIssues(null, null)).toEqual([]);
    expect(systemIssues(run({ status: 'COMPLETE' }), screens([]))).toEqual([]);
  });

  it('turns a failed nightly run into a failing issue naming the failed step', () => {
    const [issue] = systemIssues(run({}), null);
    expect(issue).toMatchObject({
      id: 'nightly:r1:FAILED',
      severity: 'failing',
      title: 'Nightly run 2026-10-08 failed: ibkr-iv',
      detail: 'steps not complete: ibkr-iv',
    });
  });

  it('makes a partial run a warning', () => {
    expect(systemIssues(run({ status: 'partial', steps: [] }), null)[0]).toMatchObject({
      severity: 'warning',
      title: 'Nightly run 2026-10-08 partial',
    });
  });

  it('names up to three screeners with no run, one issue each, and groups more', () => {
    const named = systemIssues(null, screens(['s1', 's2']));
    expect(named.map((i) => i.title)).toEqual([
      'Screener "Screener 1" has no run for 2026-10-08',
      'Screener "Screener 2" has no run for 2026-10-08',
    ]);
    expect(named[0]?.links).toEqual([{ label: 'Open screener', href: '/screeners/s1' }]);
    const grouped = systemIssues(null, screens(['s0', 's1', 's2', 's3']));
    expect(grouped).toHaveLength(1);
    expect(grouped[0]?.title).toBe('4 screeners have no run for 2026-10-08');
  });

  it('lists failing issues before warnings, and the id changes with the cause', () => {
    const issues = systemIssues(run({}), screens(['s1']));
    expect(issues.map((i) => i.severity)).toEqual(['failing', 'warning']);
    const later = systemIssues(run({ runId: 'r2' }), null);
    expect(later[0]?.id).not.toBe(issues[0]?.id);
  });
});
