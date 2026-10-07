/**
 * TopBar: the horizontal bar across the top of every screen (the banner landmark): brand, the
 * workspace switch, the workspace's NavTabs, and an end slot pushed to the far side (a search
 * box, "As of Fri 2 Oct", the latest-run note). Under 720 px (container width) the bar is two rows: brand, workspace switch and end slot, then
 * the nav full width.
 */
import type { ReactNode } from 'react';

import styles from './TopBar.module.css';

export interface TopBarProps {
  /** The product mark (e.g. `<Mono weight="medium">algotrade</Mono>`). */
  brand: ReactNode;
  /** The workspace switch (WorkspaceSwitch). */
  workspace?: ReactNode;
  /** The workspace's section links (NavTabs). */
  nav?: ReactNode;
  /** Content at the far end: a SearchInput, an as-of date, a status note. */
  end?: ReactNode;
}

export function TopBar({ brand, workspace, nav, end }: TopBarProps) {
  return (
    <header className={styles.topBar}>
      <span className={styles.brand}>{brand}</span>
      {workspace}
      {nav && <div className={styles.nav}>{nav}</div>}
      {end && <div className={styles.end}>{end}</div>}
    </header>
  );
}
