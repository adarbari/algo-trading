/**
 * LazySection: defers a heavy section (a chart, a table, its own data fetch) until it scrolls
 * near the viewport. Until then it holds the section's place with a Skeleton of `minBlockSize`,
 * so the page does not jump; the placeholder is a busy status named by `label`. Once shown the
 * children stay (scrolling away never unmounts them). Renders the children at once where
 * IntersectionObserver is missing (tests, old browsers).
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { Skeleton } from '../Skeleton';
import styles from './LazySection.module.css';

/** The reserved height, a token step: `sm` 80 px, `md` 160 px, `lg` 320 px, `xl` 480 px. */
export type LazySectionSize = 'sm' | 'md' | 'lg' | 'xl';

export interface LazySectionProps {
  /** What is loading ("Evidence curve"), read by screen readers on the placeholder. */
  label: string;
  /** The block size the placeholder reserves (default `md`). */
  minBlockSize?: LazySectionSize;
  /** How far outside the viewport the section starts to render (default `200px`). */
  rootMargin?: string;
  /** The section, rendered once it is near the viewport. */
  children: ReactNode;
}

const SKELETON_HEIGHT = { sm: 'sm', md: 'md', lg: 'lg', xl: 'lg' } as const;

export function LazySection({
  label,
  minBlockSize = 'md',
  rootMargin = '200px',
  children,
}: LazySectionProps) {
  const [shown, setShown] = useState(() => typeof IntersectionObserver === 'undefined');
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (shown || !element) return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setShown(true);
      },
      { rootMargin },
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [shown, rootMargin]);

  if (shown) return <>{children}</>;
  return (
    <div ref={host} className={styles.placeholder} data-size={minBlockSize}>
      <Skeleton variant="rect" height={SKELETON_HEIGHT[minBlockSize]} label={`Loading ${label}`} />
    </div>
  );
}
