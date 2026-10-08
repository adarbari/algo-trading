import { describe, expect, it } from 'vitest';

import type { ScreenerListItem, ScreenerSummary } from '@/entities/screen';

import { filterRows, toRows } from './rows';

const config = (configId: string, scope: string, impl = 'rules', error: string | null = null) =>
  ({
    configId,
    scope,
    kind: 'screener',
    impl,
    selection: null,
    hash: 'h',
    error,
  }) as ScreenerSummary;
const own = (screenerId: string, status = 'FINAL', presetId: string | null = null) =>
  ({ screenerId, status, latest: 1, hasDraft: false, presetId }) as ScreenerListItem;

const ROWS = toRows(
  [
    config('vrp_scanner', 'site'),
    config('short_premium', 'site', 'python'),
    config('my-vrp', 'u'),
    config('broken', 'u', 'rules', 'unknown field'),
  ],
  [own('my-vrp', 'FINAL', 'vrp_scanner'), own('broken'), own('idea', 'DRAFT')],
);

describe('toRows', () => {
  it('lists your screeners first, then the presets, each by name', () => {
    expect(ROWS.map((r) => `${r.kind}:${r.id}`)).toEqual([
      'mine:broken',
      'mine:idea',
      'mine:my-vrp',
      'preset:short_premium',
      'preset:vrp_scanner',
    ]);
  });

  it('keeps what the row needs: draft, source preset, resolve error, Python', () => {
    const by = (id: string) => ROWS.find((r) => r.id === id);
    expect(by('idea')?.draft).toBe(true);
    expect(by('my-vrp')?.presetId).toBe('vrp_scanner');
    expect(by('broken')?.error).toBe('unknown field');
    expect(by('short_premium')?.rules).toBe(false);
  });
});

describe('filterRows', () => {
  it('narrows by segment', () => {
    expect(filterRows(ROWS, 'mine', '')).toHaveLength(3);
    expect(filterRows(ROWS, 'presets', '')).toHaveLength(2);
    expect(filterRows(ROWS, 'all', '')).toHaveLength(5);
  });

  it('narrows by a name search in any case, within the segment', () => {
    expect(filterRows(ROWS, 'all', ' VRP ').map((r) => r.id)).toEqual(['my-vrp', 'vrp_scanner']);
    expect(filterRows(ROWS, 'presets', 'vrp').map((r) => r.id)).toEqual(['vrp_scanner']);
  });
});
