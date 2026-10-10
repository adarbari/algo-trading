/**
 * TextArea: a multi-line text box for a few sentences (a thesis, an answer, a note), in the same
 * box as Input and the same label, description and invalid wiring inside a Field. It grows with
 * what is typed up to `maxRows`, then scrolls; `rows` sets the height it starts at.
 */
import type { AriaAttributes, ChangeEvent, FocusEventHandler, Ref } from 'react';

import { joinIds, useFieldControl } from '../Field';
import styles from './TextArea.module.css';

export interface TextAreaProps extends Pick<AriaAttributes, 'aria-label' | 'aria-describedby'> {
  /** The text (controlled). */
  value?: string | undefined;
  /** The initial text (uncontrolled). */
  defaultValue?: string | undefined;
  /** Called with the new text on every edit. */
  onValueChange?: ((value: string) => void) | undefined;
  placeholder?: string | undefined;
  /** Lines shown before the user types more (default 3). */
  rows?: number;
  /** Shows the invalid state (a Field with an error sets this). */
  invalid?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  required?: boolean;
  name?: string;
  id?: string;
  spellCheck?: boolean;
  onBlur?: FocusEventHandler<HTMLTextAreaElement> | undefined;
  ref?: Ref<HTMLTextAreaElement>;
}

export function TextArea({
  value,
  defaultValue,
  onValueChange,
  rows = 3,
  invalid = false,
  disabled,
  required,
  id,
  'aria-describedby': describedBy,
  ...rest
}: TextAreaProps) {
  const field = useFieldControl();
  const isInvalid = invalid || Boolean(field?.invalid);
  const isDisabled = disabled ?? field?.disabled ?? false;
  return (
    <div
      className={styles.box}
      data-invalid={isInvalid || undefined}
      data-disabled={isDisabled || undefined}
    >
      <textarea
        className={styles.input}
        id={id ?? field?.id}
        rows={rows}
        value={value}
        defaultValue={defaultValue}
        onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onValueChange?.(event.target.value)}
        aria-invalid={isInvalid || undefined}
        aria-describedby={joinIds(describedBy, field?.describedBy)}
        disabled={isDisabled}
        required={required ?? field?.required}
        {...rest}
      />
    </div>
  );
}
