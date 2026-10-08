import { describe, expect, it } from 'vitest';

import { basisTone, callId, findCall, outcomeTone, sliceLabel, stamp } from './labels';
import { call, callAt, usage } from './fixtures';

describe('usage labels', () => {
  it('names a call by the key the log merges on and finds it in the latest list', () => {
    const c = call();
    expect(callId(c)).toBe('2026-10-08T14:00:00+00:00~claude~screener-draft');
    const u = usage();
    expect(findCall(u, callId(callAt(1)))).toEqual(u.recent[1]);
    expect(findCall(u, 'nope')).toBeNull();
    expect(findCall(u, null)).toBeNull();
    expect(findCall(null, callId(c))).toBeNull();
  });

  it('labels a cost basis by its name and a null group as a dash', () => {
    expect(sliceLabel('cost_basis', 'reported')).toBe('Reported (notional)');
    expect(sliceLabel('user', 'abhi')).toBe('abhi');
    expect(sliceLabel('user', null)).toBe('—');
  });

  it('tones the notional cost apart from the priced one, and a failure as negative', () => {
    expect(basisTone('reported')).not.toBe(basisTone('price'));
    expect(basisTone('bound')).toBe('warning');
    expect(outcomeTone('failed')).toBe('negative');
    expect(outcomeTone('fell_back')).toBe('warning');
  });

  it('writes the log time in UTC', () => {
    expect(stamp('2026-10-08T14:00:00.123+00:00')).toBe('2026-10-08 14:00:00 UTC');
  });
});
