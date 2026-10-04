import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useDebounced } from './use-debounced';

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('useDebounced', () => {
  it('follows the value only once it has settled', () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 300), {
      initialProps: { value: 'a' },
    });
    rerender({ value: 'b' });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    rerender({ value: 'c' });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current).toBe('a');
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current).toBe('c');
  });

  it('follows at once while immediate, and then debounces from the current value', () => {
    const { result, rerender } = renderHook(
      ({ value, immediate }) => useDebounced(value, 300, immediate),
      { initialProps: { value: 'a', immediate: true } },
    );
    rerender({ value: 'b', immediate: true });
    expect(result.current).toBe('b');
    rerender({ value: 'c', immediate: false });
    expect(result.current).toBe('b');
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(result.current).toBe('c');
  });
});
