/**
 * Checkbox: an on / off choice with its label (or a row-selection box whose label is for screen
 * readers only: `hideLabel`). Supports the mixed state (`indeterminate`) for "select all" over a
 * partial selection. The native checkbox in the accent colour: Space toggles it. A `description`
 * is announced as the box's description, not as part of its name.
 */
import { useEffect, useId, useRef, type ChangeEvent, type ReactNode } from 'react';

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
  /** Called with the new checked state (and the change event: Shift-click ranges read it). */
  onCheckedChange?: (checked: boolean, event: ChangeEvent<HTMLInputElement>) => void;
  /** Leave the box out of the Tab order (a row checkbox inside a keyboard-navigated grid). */
  excludeFromTabOrder?: boolean;
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
  excludeFromTabOrder = false,
  disabled = false,
  invalid = false,
  name,
  value,
  id,
}: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);
  const ownId = useId();
  const showDescription = !hideLabel && Boolean(description);
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
        tabIndex={excludeFromTabOrder ? -1 : undefined}
        aria-invalid={invalid || undefined}
        aria-checked={indeterminate ? 'mixed' : undefined}
        aria-labelledby={showDescription ? `${ownId}-label` : undefined}
        aria-describedby={showDescription ? `${ownId}-description` : undefined}
        onChange={(event) => onCheckedChange?.(event.target.checked, event)}
      />
      {hideLabel ? (
        <VisuallyHidden>{label}</VisuallyHidden>
      ) : (
        <span className={styles.text}>
          <span id={`${ownId}-label`}>
            <Text tone={disabled ? 'muted' : 'default'}>{label}</Text>
          </span>
          {showDescription && (
            <span id={`${ownId}-description`}>
              <Text size="sm" tone="muted">
                {description}
              </Text>
            </span>
          )}
        </span>
      )}
    </label>
  );
}
