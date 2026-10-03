/**
 * VisuallyHidden: content for screen readers only (a label for an icon-only control, the
 * meaning of a colour, a table caption). Never hides content that sighted users need.
 */
import type { ReactNode } from 'react';

import styles from './VisuallyHidden.module.css';

export interface VisuallyHiddenProps {
  /** `span` (inline, default) or `div` (block content such as a caption). */
  as?: 'span' | 'div';
  /** Target of an `aria-labelledby` / `aria-describedby`. */
  id?: string;
  children: ReactNode;
}

export function VisuallyHidden({ as: Element = 'span', id, children }: VisuallyHiddenProps) {
  return (
    <Element className={styles.visuallyHidden} id={id}>
      {children}
    </Element>
  );
}
