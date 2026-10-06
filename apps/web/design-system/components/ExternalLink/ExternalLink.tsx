/**
 * ExternalLink: a link to a page outside the app (a FRED series, a Fed note, a paper): the
 * title in the accent colour with a trailing "external" mark, opened in a new tab with
 * `noopener noreferrer`. Its words say where it goes, and a screen reader hears "opens in a
 * new tab". Router links are not this: the top bar's NavTabs renders those.
 */
import { Icon } from '../Icon';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';

import styles from './ExternalLink.module.css';

export interface ExternalLinkProps {
  /** The page's address (an absolute http(s) URL). */
  href: string;
  /** What the page is ("Chicago Fed NFCI"): the visible text. */
  children: string;
  /** Smaller text for a dense list (`sm`), the body size (default) or the surrounding text's (`inherit`, inside a sentence). */
  size?: 'sm' | 'base' | 'inherit';
  /** Hover text about the page ("Chicago Fed, weekly"). */
  title?: string;
}

export function ExternalLink({ href, children, size = 'base', title }: ExternalLinkProps) {
  return (
    <a
      className={styles.link}
      data-size={size}
      title={title}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
      <Icon name="external" size="sm" />
      <VisuallyHidden>{', opens in a new tab'}</VisuallyHidden>
    </a>
  );
}
