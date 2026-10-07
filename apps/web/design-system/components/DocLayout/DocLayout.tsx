/**
 * DocLayout: the frame of a reference page (the Guide): a narrow `rail` to find things, the
 * `children` as the article (a reading width, the content is the hero) and an optional `aside`
 * on the end (a page's "On this page" list). The columns wrap under each other when the page is
 * narrow. `DocSection` is the anchor of one part of the article, the target of an "On this page"
 * link (the content brings its own heading and landmark); it clears the top bar when scrolled to.
 */
import type { ReactNode } from 'react';

import styles from './DocLayout.module.css';

export interface DocLayoutProps {
  /** The side rail: a search and a NavList. */
  rail?: ReactNode;
  /** The list on the end: a NavList of this page's anchors. */
  aside?: ReactNode;
  /** The article: DocSections and other blocks, one column. */
  children: ReactNode;
}

export function DocLayout({ rail, aside, children }: DocLayoutProps) {
  return (
    <div className={styles.layout}>
      {rail && <div className={styles.rail}>{rail}</div>}
      <article className={styles.article} data-wide={aside ? undefined : true}>
        {children}
      </article>
      {aside && <div className={styles.aside}>{aside}</div>}
    </div>
  );
}

export interface DocSectionProps {
  /** The anchor: `#id` in the URL scrolls here. */
  id: string;
  children: ReactNode;
}

export function DocSection({ id, children }: DocSectionProps) {
  return (
    <div id={id} className={styles.section}>
      {children}
    </div>
  );
}
