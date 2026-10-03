/**
 * Button: an action. `primary` (the one main action of a view: solid accent), `secondary` (the
 * default: bordered), `ghost` (quiet, in toolbars and rows) and `dashed` (add something:
 * "+ Add criterion"). Height follows the density's control height; `sm` is the small inline
 * size (panel headers, chips row). `loading` keeps the label, shows a spinner, and blocks clicks.
 */
import type { AriaAttributes, MouseEventHandler, ReactNode, Ref } from 'react';

import { Icon, type IconName } from '../Icon';
import styles from './Button.module.css';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'dashed';

export interface ButtonProps extends Pick<
  AriaAttributes,
  | 'aria-label'
  | 'aria-describedby'
  | 'aria-expanded'
  | 'aria-controls'
  | 'aria-haspopup'
  | 'aria-pressed'
> {
  /** Visual weight: `primary` once per view, `secondary` (default), `ghost`, `dashed` (add). */
  variant?: ButtonVariant;
  /** `md` (density control height, default) or `sm` (compact inline). */
  size?: 'sm' | 'md';
  /** An icon before the label (e.g. `plus` for add, `refresh` for re-run). */
  icon?: IconName;
  /** An icon after the label (e.g. `chevron-down` for a menu, `external` for a link out). */
  iconEnd?: IconName;
  /** Busy: shows a spinner in place of the icon, sets aria-busy and ignores clicks. */
  loading?: boolean;
  disabled?: boolean;
  /** Form role; `button` by default so it never submits by accident. */
  type?: 'button' | 'submit' | 'reset';
  /** Stretch to the container's width (stacked forms on phones). */
  fullWidth?: boolean;
  onClick?: MouseEventHandler<HTMLButtonElement>;
  ref?: Ref<HTMLButtonElement>;
  id?: string;
  children: ReactNode;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  iconEnd,
  loading = false,
  disabled = false,
  type = 'button',
  fullWidth = false,
  onClick,
  children,
  ...rest
}: ButtonProps) {
  const iconSize = size === 'sm' ? 'sm' : 'md';
  return (
    <button
      type={type}
      className={styles.button}
      data-variant={variant}
      data-size={size}
      data-full-width={fullWidth || undefined}
      disabled={disabled}
      aria-disabled={loading || undefined}
      aria-busy={loading || undefined}
      onClick={loading ? undefined : onClick}
      {...rest}
    >
      {loading ? (
        <Icon name="spinner" spin size={iconSize} />
      ) : (
        icon && <Icon name={icon} size={iconSize} />
      )}
      <span className={styles.label}>{children}</span>
      {iconEnd && !loading && <Icon name={iconEnd} size={iconSize} />}
    </button>
  );
}
