import { describe, expect, it } from 'vitest';

import type { ColumnInfo } from '@/entities/feature';

import { tablePlan } from './plan';

const info = (name: string): ColumnInfo => ({
  name,
  description: name,
  format: 'NUMBER',
  unit: null,
  dtype: 'float',
  nullMeaning: '',
  licence: 'open',
  scope: 'site',
});

describe('tablePlan', () => {
  it('shows the columns asked for, not the companions the server sent with them', () => {
    const served = [
      info('feature.pct_from_high_avail'),
      info('rollup.price_history@v1.range_sessions'),
    ];
    const ids = (shown?: string[]) => tablePlan(served, shown).map((c) => c.id);
    expect(ids(['feature.pct_from_high_avail'])).toEqual(['symbol', 'feature.pct_from_high_avail']);
    expect(ids()).toHaveLength(3);
  });
});
