/**
 * Chip: a compact label for a filter or a choice. Static (a tag), a filter chip that toggles
 * (`onSelectedChange`: a pressed / not-pressed button, selected in the accent tint), removable
 * (`onRemove`: an × button named "Remove <label>"), or the dashed "add" chip (`variant="dashed"`
 * with `onClick`: "+ Filter"). Several in a wrapping Stack form a filter bar.
 */
import { useState, type MouseEventHandler } from 'react';

import { Icon, type IconName } from '../Icon';
import { IconButton } from '../IconButton';
import styles from './Chip.module.css';

export interface ChipProps {
  /** The text ("Near 52w high", "Liquidity: High"). */
  label: string;
  /** Selected (controlled): a filter that is on. */
  selected?: boolean;
  /** Initially selected (uncontrolled). */
  defaultSelected?: boolean;
  /** Makes the chip a toggle button; called with the new selected state. */
  onSelectedChange?: (selected: boolean) => void;
  /** Makes the chip an action button (the dashed "add" chip opens a picker). */
  onClick?: MouseEventHandler<HTMLButtonElement>;
  /** Adds a remove button named "Remove <label>". */
  onRemove?: () => void;
  /** `default` or `dashed` (add something). */
  variant?: 'default' | 'dashed';
  /** A leading icon (`plus` on the add chip, `filter`). */
  icon?: IconName;
  disabled?: boolean;
}

export function Chip({
  label,
  selected,
  defaultSelected = false,
  onSelectedChange,
  onClick,
  onRemove,
  variant = 'default',
  icon,
  disabled = false,
}: ChipProps) {
  const [internal, setInternal] = useState(defaultSelected);
  const toggle = onSelectedChange !== undefined || selected !== undefined;
  const isSelected = toggle ? (selected ?? internal) : false;
  const content = (
    <>
      {icon && <Icon name={icon} size="sm" />}
      <span className={styles.label}>{label}</span>
    </>
  );
  return (
    <span
      className={styles.chip}
      data-variant={variant}
      data-selected={isSelected || undefined}
      data-disabled={disabled || undefined}
      data-removable={onRemove ? true : undefined}
    >
      {toggle || onClick ? (
        <button
          type="button"
          className={styles.main}
          data-interactive=""
          aria-pressed={toggle ? isSelected : undefined}
          disabled={disabled}
          onClick={(event) => {
            if (toggle) {
              if (selected === undefined) setInternal(!isSelected);
              onSelectedChange?.(!isSelected);
            }
            onClick?.(event);
          }}
        >
          {content}
        </button>
      ) : (
        <span className={styles.main}>{content}</span>
      )}
      {onRemove && (
        <IconButton
          icon="close"
          label={`Remove ${label}`}
          size="sm"
          disabled={disabled}
          onClick={onRemove}
        />
      )}
    </span>
  );
}
