/**
 * ExpandLink: a link-styled button that opens a block in place, under the row or paragraph it
 * sits in (a screener's win rate opening one record per edge). A caret turns when open;
 * `aria-expanded` carries the state. It is a control, not a navigation: a link to another page
 * is a TextLink.
 */
import type { ReactNode } from 'react';

import { Icon } from '../Icon';
import styles from './ExpandLink.module.css';

export interface ExpandLinkProps {
  /** Whether the block it opens is shown. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The id of the block it opens, set while that block is rendered. */
  controls?: string;
  /** The words of the link ("Win 58% vs 51% base"). */
  children: ReactNode;
}

export function ExpandLink({ open, onOpenChange, controls, children }: ExpandLinkProps) {
  return (
    <button
      type="button"
      className={styles.link}
      aria-expanded={open}
      aria-controls={open ? controls : undefined}
      onClick={() => {
        onOpenChange(!open);
      }}
    >
      <span className={styles.text}>{children}</span>
      <span className={styles.caret} data-open={open || undefined}>
        <Icon name="chevron-down" size="sm" />
      </span>
    </button>
  );
}
