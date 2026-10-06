import { describe, expect, it } from 'vitest';

import { segmentTone, statusHint, statusTone } from './status';

describe('status tones', () => {
  it('maps item codes, run states and check results', () => {
    expect(statusTone('OK')).toBe('positive');
    expect(statusTone('complete')).toBe('positive');
    expect(statusTone('STALE_DATA: chain is for 2026-10-01')).toBe('warning');
    expect(statusTone('partial')).toBe('warning');
    expect(statusTone('FETCH_ERROR: HTTP 403')).toBe('negative');
    expect(statusTone('FAIL')).toBe('negative');
    expect(statusTone('NO_CHAIN')).toBe('neutral');
    expect(statusTone('SUCCEEDED')).toBe('positive');
    expect(statusTone('WAIVED')).toBe('warning');
    expect(statusTone('NOT_RUN')).toBe('negative');
    expect(statusTone('WAITING')).toBe('info');
    expect(segmentTone('WAITING')).toBe('info');
    expect(segmentTone('NO_CHAIN')).toBe('muted');
    expect(segmentTone('OK')).toBe('positive');
  });

  it('explains the common item codes', () => {
    expect(statusHint('STALE_DATA: chain is for 2026-10-01')).toMatch(/UNKNOWN/);
    expect(statusHint('WAITING')).toMatch(/not published/);
    expect(statusHint('SOMETHING_ELSE')).toBeUndefined();
  });
});
