/**
 * Checkbox: an on / off choice with its label (or a row-selection box whose label is for screen
 * readers only: `hideLabel`). Supports the mixed state (`indeterminate`) for "select all" over a
 * partial selection. The native checkbox in the accent colour: Space toggles it.
 */
import { useEffect, useRef, type ReactNode } from 'react';

import { Text } from '../../primitives/Text';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import styles from './Checkbox.module.css';

export interface CheckboxProps {
  /** What is chosen ("Select AAPL", "Include leveraged ETFs"). */
  label: string;
  /** Secondary text under the label. */
  description?: ReactNode;
  /** Keep the label for screen readers only (row selection in a table). */
  hideLabel?: boolean;
  /** Checked (controlled). */
  checked?: boolean;
  /** Initially checked (uncontrolled). */
  defaultChecked?: boolean;
  /** The mixed state of a "select all" box over a partial selection. */
  indeterminate?: boolean;
  /** Called with the new checked state. */
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  invalid?: boolean;
  name?: string;
  value?: string;
  id?: string;
}

export function Checkbox({
  label,
  description,
  hideLabel = false,
  checked,
  defaultChecked,
  indeterminate = false,
  onCheckedChange,
  disabled = false,
  invalid = false,
  name,
  value,
  id,
}: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <label
      className={styles.checkbox}
      data-disabled={disabled || undefined}
      data-hide-label={hideLabel || undefined}
    >
      <input
        ref={ref}
        className={styles.box}
        type="checkbox"
        id={id}
        name={name}
        value={value}
        checked={checked}
        defaultChecked={defaultChecked}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-checked={indeterminate ? 'mixed' : undefined}
        onChange={(event) => onCheckedChange?.(event.target.checked)}
      />
      {hideLabel ? (
        <VisuallyHidden>{label}</VisuallyHidden>
      ) : (
        <span className={styles.text}>
          <Text tone={disabled ? 'muted' : 'default'}>{label}</Text>
          {description && (
            <Text size="sm" tone="muted">
              {description}
            </Text>
          )}
        </span>
      )}
    </label>
  );
}
