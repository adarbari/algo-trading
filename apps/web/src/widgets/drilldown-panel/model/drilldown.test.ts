import { describe, expect, it } from 'vitest';

import type { CellDetail } from '@/entities/ingestion';
import type { RunDetail } from '@/entities/run';

import { examplesText, fetchTiers, primaryRun, statusSegments } from './drilldown';

const run = (
  run_id: string,
  job: string,
  items_total: number,
  extra: Partial<RunDetail> = {},
): RunDetail => ({
  run_id,
  job,
  session: '2026-10-02',
  status: 'partial',
  started_at: '2026-10-03T09:35:02Z',
  finished_at: '2026-10-03T09:55:00Z',
  duration_s: 1198,
  items_total,
  items_by_status: { OK: 3624, STALE_DATA: 515, NO_CHAIN: 63 },
  failures: [],
  stats: {},
  ...extra,
});

const detail: CellDetail = {
  cell: {
    dataset: 'chains/option_quotes',
    session: '2026-10-02',
    status: 'PARTIAL',
    present: 3623,
    expected: 4203,
    basis: 'optionable universe, fetch OK',
    run_ids: [],
  },
  job: 'option_chains',
  groups: [],
  runs: [
    run('migrate', 'migrate_ids', 0),
    run('chains-1', 'option_chains', 4204),
    run('chains-2', 'option_chains', 0),
  ],
};

describe('drill-down model', () => {
  it('explains the cell with the latest run of its job that has items', () => {
    expect(primaryRun(detail)?.run_id).toBe('chains-1');
    expect(primaryRun({ ...detail, job: 'other' })?.run_id).toBe('chains-2');
  });

  it('splits the run items by status, else present vs missing rows', () => {
    expect(statusSegments(detail, primaryRun(detail))).toEqual([
      { id: 'OK', label: 'Ok', value: 3624, tone: 'positive' },
      { id: 'STALE_DATA', label: 'Stale data', value: 515, tone: 'warning' },
      { id: 'NO_CHAIN', label: 'No chain', value: 63, tone: 'muted' },
    ]);
    expect(statusSegments(detail, undefined)).toEqual([
      { id: 'present', label: 'Present', value: 3623, tone: 'positive' },
      { id: 'missing', label: 'Missing', value: 580, tone: 'negative' },
    ]);
  });

  it('reads the fetch tiers a chains run recorded', () => {
    const tiers = fetchTiers(
      run('c', 'option_chains', 1, {
        stats: { order_tiers: { priority: 536, liquidity: 1840, rest: 1827 } },
      }),
    );
    expect(tiers.map((t) => [t.id, t.value])).toEqual([
      ['priority', 536],
      ['liquidity', 1840],
      ['rest', 1827],
    ]);
    expect(fetchTiers(run('c', 'option_chains', 1))).toEqual([]);
  });

  it('lists examples with the rest counted', () => {
    expect(examplesText(['ACIU', 'ALLT'], 515)).toBe('ACIU · ALLT · … 513 more');
    expect(examplesText(['ENLV', 'RNA'], 2)).toBe('ENLV · RNA');
  });
});
