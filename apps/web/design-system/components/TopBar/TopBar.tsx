/**
 * TopBar: the horizontal bar across the top of every screen (the banner landmark): brand, the
 * workspace's NavTabs, a utility slot for links that belong to no workspace (the Guide) and an
 * end slot pushed to the far side (status chips, the account menu, "As of Fri 2 Oct"). The
 * workspace switch is not in the bar: it lives in the AccountMenu (owner decision 2026-10-07).
 * Under 720 px (container width) the bar is a two-row grid: brand, utility and end on the first
 * row (the end slot keeps one line and scrolls sideways), the nav on the second.
 */
import type { ReactNode } from 'react';

import styles from './TopBar.module.css';

export interface TopBarProps {
  /** The product mark (e.g. `<Mono weight="medium">algotrade</Mono>`). */
  brand: ReactNode;
  /** The workspace's section links (NavTabs). */
  nav?: ReactNode;
  /** A utility link on the far side, before `end` (a TextLink to the Guide), in every workspace. */
  utility?: ReactNode;
  /** Content at the far end: a SearchInput, an as-of date, a status note. */
  end?: ReactNode;
}

export function TopBar({ brand, nav, utility, end }: TopBarProps) {
  return (
    <header className={styles.topBar}>
      <span className={styles.brand}>{brand}</span>
      {nav && <div className={styles.nav}>{nav}</div>}
      {utility && <div className={styles.utility}>{utility}</div>}
      {end && <div className={styles.end}>{end}</div>}
    </header>
  );
}
