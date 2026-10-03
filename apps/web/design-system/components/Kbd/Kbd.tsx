/**
 * Kbd: a keyboard key or shortcut as it is pressed ("/", "Esc", "Ctrl + K"), in the mono face
 * with a thin key outline. `keys` renders a chord: each key outlined, joined by "+". Use it in
 * hints, tooltips and help text; it is text, not a control.
 */
import { Fragment } from 'react';

import styles from './Kbd.module.css';

export interface KbdProps {
  /** The keys of one shortcut, pressed together: `['Ctrl', 'K']`, `['/']`. */
  keys: readonly string[];
  /** `sm` (default, inline in body text) or `xs` (in captions and tooltips). */
  size?: 'sm' | 'xs';
}

export function Kbd({ keys, size = 'sm' }: KbdProps) {
  return (
    <kbd className={styles.chord} data-size={size}>
      {keys.map((key, index) => (
        <Fragment key={`${key}-${String(index)}`}>
          {index > 0 && <span className={styles.plus}>+</span>}
          <kbd className={styles.key}>{key}</kbd>
        </Fragment>
      ))}
    </kbd>
  );
}
