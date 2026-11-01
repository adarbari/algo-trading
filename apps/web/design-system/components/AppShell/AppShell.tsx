/**
 * AppShell: the frame of every screen: a skip link, the TopBar, an optional status strip under
 * it (a StatusStrip), the main content region and an optional footer (data status, risk line).
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
  /** The line under the content on every page (data status and the risk statement); absent: nothing. */
  footer?: ReactNode;
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
  footer,
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
      {footer !== undefined && footer !== null && (
        <footer className={styles.footer}>{footer}</footer>
      )}
    </div>
  );
}
