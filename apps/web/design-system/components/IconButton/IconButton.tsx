/**
 * IconButton: a square, icon-only action (remove a row, clear a search, open a menu). `label`
 * is required: it is the accessible name and the hover tooltip. Quiet (`ghost`) by default, as
 * in the mockups' remove-criterion button; `secondary` adds the control border.
 */
import type { AriaAttributes, MouseEventHandler, Ref } from 'react';

import { Icon, type IconName } from '../Icon';
import styles from './IconButton.module.css';

export interface IconButtonProps extends Pick<
  AriaAttributes,
  'aria-expanded' | 'aria-controls' | 'aria-haspopup' | 'aria-pressed' | 'aria-describedby'
> {
  /** The glyph. */
  icon: IconName;
  /** What the button does ("Remove criterion"): the accessible name and the tooltip. */
  label: string;
  /** `ghost` (default: no border until hover) or `secondary` (bordered). */
  variant?: 'ghost' | 'secondary';
  /** `md` (density control height, default) or `sm` (inside chips and inputs). */
  size?: 'sm' | 'md';
  disabled?: boolean;
  onClick?: MouseEventHandler<HTMLButtonElement>;
  /** -1 keeps it out of the tab order (a control reachable another way, e.g. Escape). */
  tabIndex?: 0 | -1;
  ref?: Ref<HTMLButtonElement>;
}

export function IconButton({
  icon,
  label,
  variant = 'ghost',
  size = 'md',
  disabled = false,
  onClick,
  ...rest
}: IconButtonProps) {
  return (
    <button
      type="button"
      className={styles.iconButton}
      data-variant={variant}
      data-size={size}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      {...rest}
    >
      <Icon name={icon} size={size === 'sm' ? 'sm' : 'md'} />
    </button>
  );
}
