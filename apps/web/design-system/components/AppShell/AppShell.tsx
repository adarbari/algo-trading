/**
 * AppShell: the frame of every screen: a skip link, the TopBar, an optional status strip under
 * it (a StatusStrip) and the main content region.
 * `page` layout centres content up to the page width (1600 px) with page padding and a gap
 * between sections; `full` gives the page the whole width with no padding (split views such as
 * Explore). Padding tightens at phone width.
 */
import { useId, type ReactNode } from 'react';

import styles from './AppShell.module.css';

export interface AppShellProps {
  /** The bar across the top (TopBar). */
  topBar: ReactNode;
  /** A slim strip under the bar, on every page (a StatusStrip); absent: nothing. */
  strip?: ReactNode;
  /** `page` (centred, max page width, padded; default) or `full` (edge to edge). */
  layout?: 'page' | 'full';
  /** Text of the skip link that jumps past the top bar to the content. */
  skipLabel?: string;
  /** The page. */
  children: ReactNode;
}

export function AppShell({
  topBar,
  strip,
  layout = 'page',
  skipLabel = 'Skip to content',
  children,
}: AppShellProps) {
  const mainId = `main${useId().replace(/[^\w-]/g, '')}`;
  return (
    <div className={styles.shell}>
      <a className={styles.skip} href={`#${mainId}`}>
        {skipLabel}
      </a>
      {topBar}
      {strip}
      <main id={mainId} tabIndex={-1} className={styles.main} data-layout={layout}>
        {children}
      </main>
    </div>
  );
}
