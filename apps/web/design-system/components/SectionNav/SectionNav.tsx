/**
 * SectionNav: a sticky in-page navigation for one long scroll (Now, Why, History). Each item
 * scrolls to the element with its `id` (a `Box` with that `id`) and the one in view is marked
 * `aria-current="location"`. A row of quiet links that scrolls sideways on a phone. For
 * switching views inside a page use Tabs, for a workspace's pages NavTabs.
 */
import { useEffect, useState, type MouseEvent } from 'react';

import styles from './SectionNav.module.css';

export interface SectionNavItem {
  /** The `id` of the section element this item scrolls to. */
  id: string;
  label: string;
}

export interface SectionNavProps {
  /** The sections, in page order. */
  items: readonly SectionNavItem[];
  /** The navigation landmark's name ("Regime sections"). */
  'aria-label': string;
}

export function SectionNav({ items, 'aria-label': ariaLabel }: SectionNavProps) {
  const [active, setActive] = useState<string | undefined>(items[0]?.id);
  // Follow the scroll: the last section whose top has passed the upper part of the viewport.
  // jsdom and old browsers have no IntersectionObserver; the nav then marks the clicked item.
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return undefined;
    const seen = new Set<string>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) seen.add(entry.target.id);
          else seen.delete(entry.target.id);
        }
        const first = items.find((item) => seen.has(item.id));
        if (first) setActive(first.id);
      },
      { rootMargin: '0px 0px -60% 0px' },
    );
    for (const item of items) {
      const element = document.getElementById(item.id);
      if (element) observer.observe(element);
    }
    return () => {
      observer.disconnect();
    };
  }, [items]);

  const go = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    const target = document.getElementById(id);
    if (!target) return;
    event.preventDefault();
    setActive(id);
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- absent in jsdom
    target.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };

  return (
    <nav aria-label={ariaLabel} className={styles.nav}>
      {items.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          className={styles.link}
          aria-current={item.id === active ? 'location' : undefined}
          onClick={(event) => {
            go(event, item.id);
          }}
        >
          {item.label}
        </a>
      ))}
    </nav>
  );
}
