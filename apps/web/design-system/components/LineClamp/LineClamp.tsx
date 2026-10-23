/**
 * LineClamp: a block of text cut to two lines with an ellipsis (a one-line description under a
 * name that may wrap on a phone). The full text stays in the DOM and in `title`.
 */
import type { ReactNode } from 'react';

import styles from './LineClamp.module.css';

export interface LineClampProps {
  /** The full text as a tooltip, for the part the clamp cuts. */
  title?: string;
  children: ReactNode;
}

export function LineClamp({ title, children }: LineClampProps) {
  return (
    <div className={styles.clamp} title={title}>
      {children}
    </div>
  );
}
