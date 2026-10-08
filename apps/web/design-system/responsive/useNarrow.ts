/**
 * useNarrow: whether an element is narrower than a breakpoint token, for a component whose tree
 * (not only its CSS) changes on a phone (a table that flips its axes, a detail that moves into a
 * sheet). CSS-only changes use a container query instead. A ResizeObserver measures the element;
 * before the first measurement the viewport width is the guess, so a phone does not flash the
 * wide layout.
 */
import { useEffect, useRef, useState, type RefObject } from 'react';

import { breakpoint, type Breakpoint } from '../tokens';

/** The viewport's guess before the element is measured (false outside a browser). */
function guess(limit: number): boolean {
  return typeof window !== 'undefined' && window.innerWidth < limit;
}

/**
 * A ref to put on the measured element and whether its width is under `size` (default `lg`).
 * An element with no width yet (hidden, not laid out) keeps the last answer.
 */
export function useNarrow(size: Breakpoint = 'lg'): [RefObject<HTMLDivElement | null>, boolean] {
  const limit = breakpoint[size];
  const ref = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(() => guess(limit));
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width > 0) setNarrow(width < limit);
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [limit]);
  return [ref, narrow];
}
