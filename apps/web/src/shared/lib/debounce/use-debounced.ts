/**
 * A value that follows `value` only after it has stopped changing for `delayMs`. With
 * `immediate` it follows at once (and stays in step, so switching it off starts from the
 * current value): a freshly loaded value should not wait, only edits should.
 */
import { useEffect, useState } from 'react';

export function useDebounced<T>(value: T, delayMs: number, immediate = false): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    if (immediate) {
      setDebounced(value);
      return undefined;
    }
    const timer = setTimeout(() => {
      setDebounced(value);
    }, delayMs);
    return () => {
      clearTimeout(timer);
    };
  }, [value, delayMs, immediate]);
  return immediate ? value : debounced;
}
