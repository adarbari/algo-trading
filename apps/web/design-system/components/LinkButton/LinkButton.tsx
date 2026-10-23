/**
 * LinkButton: a button that reads as a link and goes somewhere (a screener's pick count opening
 * its screener): accent text, a chevron after it that nudges on hover, an underline on hover and
 * the app's focus ring. It runs a callback; a link with an address is a TextLink, and a control
 * that opens a block in place is an ExpandLink.
 */
import type { MouseEventHandler } from 'react';

import { Icon } from '../Icon';
import styles from './LinkButton.module.css';

export interface LinkButtonProps {
  /** The words ("12 picks"). */
  children: string;
  /** Where it goes, when the words alone do not say ("Open Breakout: 12 picks"). */
  'aria-label'?: string;
  onClick: MouseEventHandler<HTMLButtonElement>;
}

export function LinkButton({ children, onClick, ...rest }: LinkButtonProps) {
  return (
    <button type="button" className={styles.link} onClick={onClick} {...rest}>
      <span className={styles.text}>{children}</span>
      <span className={styles.arrow}>
        <Icon name="chevron-right" size="sm" />
      </span>
    </button>
  );
}
