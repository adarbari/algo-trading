import { describe, expect, it } from 'vitest';

import { runFixture } from '@/entities/harness-run';

import { summaryItems } from './HarnessRunSummary';

describe('summaryItems', () => {
  it('counts the last 7 days, their failures and exploratory runs', () => {
    const items = summaryItems([
      runFixture({ runId: 'a', status: 'failed', startedAt: '2026-10-22T10:00:00Z' }),
      runFixture({
        runId: 'b',
        status: 'complete',
        startedAt: '2026-10-21T10:00:00Z',
        exploratory: true,
      }),
      runFixture({ runId: 'c', status: 'complete', startedAt: '2026-09-01T10:00:00Z' }),
    ]);
    expect(items.find((i) => i.id === 'recent')).toMatchObject({ value: '2', sub: '1 failed' });
    expect(items.find((i) => i.id === 'exploratory')?.value).toBe('1');
  });

  it('says no run is recorded for an empty list', () => {
    expect(summaryItems([]).find((i) => i.id === 'latest')?.sub).toBe('no run recorded');
  });
});
