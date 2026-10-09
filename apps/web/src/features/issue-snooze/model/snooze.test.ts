import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadSnoozes, parseSnoozes, SNOOZE_MS, withSnooze } from './snooze';
import { useSnooze } from './use-snooze';

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('snoozes', () => {
  it('keeps only well-formed entries that have not ended', () => {
    const raw = JSON.stringify({ live: 200, over: 50, bad: 'x' });
    expect(parseSnoozes(raw, 100)).toEqual({ live: 200 });
    expect(parseSnoozes('not json', 100)).toEqual({});
    expect(parseSnoozes('[1]', 100)).toEqual({});
    expect(parseSnoozes(null, 100)).toEqual({});
  });

  it('ends a snooze 24 hours after it starts', () => {
    expect(withSnooze({}, 'a', 1000)).toEqual({ a: 1000 + SNOOZE_MS });
  });

  it('survives storage that throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(loadSnoozes(0)).toEqual({});
  });
});

describe('useSnooze', () => {
  const items = [{ id: 'a' }, { id: 'b' }];

  it('hides a snoozed issue, remembers it, and brings it back after 24 hours', () => {
    let now = 1_000;
    const { result, rerender } = renderHook(() => useSnooze(() => now));
    expect(result.current.visible(items)).toHaveLength(2);
    act(() => {
      result.current.snooze('a');
    });
    expect(result.current.visible(items)).toEqual([{ id: 'b' }]);
    expect(localStorage.getItem('algotrade.snoozedIssues')).toContain('"a"');
    // A reload in the same browser still hides it.
    expect(renderHook(() => useSnooze(() => now)).result.current.visible(items)).toHaveLength(1);
    now += SNOOZE_MS + 1;
    rerender();
    expect(result.current.visible(items)).toHaveLength(2);
  });

  it('shows an issue whose id changed', () => {
    const { result } = renderHook(() => useSnooze(() => 1));
    act(() => {
      result.current.snooze('nightly:r1:FAILED');
    });
    expect(result.current.visible([{ id: 'nightly:r2:FAILED' }])).toHaveLength(1);
  });

  it('still hides for this page load when storage throws on write', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('full');
    });
    const { result } = renderHook(() => useSnooze(() => 1));
    act(() => {
      result.current.snooze('a');
    });
    expect(result.current.visible(items)).toEqual([{ id: 'b' }]);
  });
});
