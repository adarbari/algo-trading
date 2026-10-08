import { describe, expect, it } from 'vitest';

import { row } from './fixtures';
import { rangeText, rowKey, rowLabel, stamp, statusTone } from './labels';

describe('harness run labels', () => {
  it('tones a status and words a timestamp and a range', () => {
    expect(statusTone('complete')).toBe('positive');
    expect(statusTone('failed')).toBe('negative');
    expect(statusTone('queued')).toBe('neutral');
    expect(stamp('2026-10-05T02:10:33+00:00')).toBe('2026-10-05 02:10 UTC');
    expect(rangeText('2012-01-03', '2026-10-02')).toBe('2012-01-03 to 2026-10-02');
    expect(rangeText(null, '2026-10-02')).toBe('… to 2026-10-02');
  });

  it('labels a row by variant, role and edge variant, and keys it by its slice', () => {
    expect(rowLabel(row())).toBe('momentum_12_1 (screener)');
    expect(rowLabel(row({ edgeVariant: 'fast' }))).toBe('fast · momentum_12_1 (screener)');
    expect(rowKey(row())).toBe('main/screener/momentum_12_1/21/frozen/2024-01-01');
  });
});
