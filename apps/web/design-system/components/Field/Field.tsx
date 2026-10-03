/**
 * Field: a form control's label, hint and error, wired for screen readers. Wrap one Input,
 * SearchInput, NumberInput, Select or Combobox: the control picks up the field's id (so the
 * label names it), `aria-describedby` (hint, then error), `aria-invalid` and `required` without
 * any props. `inline` puts the label in a fixed column beside the control (settings forms).
 */
import { createContext, useContext, useId, type ReactNode } from 'react';

import { Text } from '../../primitives/Text';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { Icon } from '../Icon';
import styles from './Field.module.css';

/** What a control inside a Field reads to wire itself up. */
export interface FieldControl {
  id: string;
  /** The label element's id (for popups that are named by the field, e.g. a listbox). */
  labelId: string;
  describedBy: string | undefined;
  invalid: boolean;
  required: boolean;
  disabled: boolean;
}

const FieldContext = createContext<FieldControl | null>(null);

/** The enclosing Field's wiring, or null outside a Field (design-system controls only). */
export function useFieldControl(): FieldControl | null {
  return useContext(FieldContext);
}

/** Joins aria-describedby id lists, skipping blanks. */
export function joinIds(...ids: (string | undefined)[]): string | undefined {
  const joined = ids.filter(Boolean).join(' ');
  return joined || undefined;
}

export interface FieldProps {
  /** What the control is for ("Threshold", "Universe"). */
  label: string;
  /** Short help under the control (units, format, what it affects). */
  hint?: ReactNode;
  /** The validation message; marks the control invalid and is announced with it. */
  error?: string | undefined;
  /** Marks the control required (an asterisk on the label, `required` on the control). */
  required?: boolean;
  /** Disables the control inside. */
  disabled?: boolean;
  /** `stack` (label above, default) or `inline` (label column beside the control). */
  layout?: 'stack' | 'inline';
  /** Keep the label for screen readers only (a control whose purpose is obvious in context). */
  hideLabel?: boolean;
  /** The control's id, if the caller needs it (generated otherwise). */
  id?: string;
  /** Exactly one design-system control. */
  children: ReactNode;
}

export function Field({
  label,
  hint,
  error,
  required = false,
  disabled = false,
  layout = 'stack',
  hideLabel = false,
  id,
  children,
}: FieldProps) {
  const generated = useId();
  const controlId = id ?? `${generated}control`;
  const hintId = hint ? `${generated}hint` : undefined;
  const errorId = error ? `${generated}error` : undefined;
  const control: FieldControl = {
    id: controlId,
    labelId: `${generated}label`,
    describedBy: joinIds(hintId, errorId),
    invalid: Boolean(error),
    required,
    disabled,
  };
  const labelText = (
    <>
      {label}
      {required && (
        <span className={styles.required} aria-hidden="true">
          {' '}
          *
        </span>
      )}
    </>
  );
  return (
    <div className={styles.field} data-layout={layout} data-disabled={disabled || undefined}>
      <label htmlFor={controlId} id={control.labelId} className={styles.label}>
        {hideLabel ? <VisuallyHidden>{labelText}</VisuallyHidden> : labelText}
      </label>
      <div className={styles.control}>
        <FieldContext value={control}>{children}</FieldContext>
        {hint && (
          <span id={hintId} className={styles.message}>
            <Text size="sm" tone="muted">
              {hint}
            </Text>
          </span>
        )}
        {error && (
          <span id={errorId} className={styles.message}>
            <Icon name="alert" size="sm" tone="negative" />
            <Text size="sm" tone="negative">
              {error}
            </Text>
          </span>
        )}
      </div>
    </div>
  );
}
