/**
 * Input: a single-line text box at the density's control height, with optional `start` / `end`
 * adornments (an icon, a unit, a clear button). Inside a Field it is labelled, described and
 * marked invalid automatically; outside one, give `aria-label`. SearchInput, NumberInput and
 * Combobox are built on it.
 */
import type {
  AriaAttributes,
  ChangeEvent,
  FocusEventHandler,
  KeyboardEventHandler,
  MouseEventHandler,
  ReactNode,
  Ref,
} from 'react';

import { joinIds, useFieldControl } from '../Field';
import styles from './Input.module.css';

export interface InputProps extends Pick<
  AriaAttributes,
  | 'aria-label'
  | 'aria-labelledby'
  | 'aria-describedby'
  | 'aria-expanded'
  | 'aria-controls'
  | 'aria-activedescendant'
  | 'aria-autocomplete'
  | 'aria-valuemin'
  | 'aria-valuemax'
  | 'aria-valuenow'
  | 'aria-valuetext'
> {
  /** The text (controlled). */
  value?: string | undefined;
  /** The initial text (uncontrolled). */
  defaultValue?: string | undefined;
  /** Called with the new text on every edit. */
  onValueChange?: ((value: string) => void) | undefined;
  placeholder?: string | undefined;
  /** `text` (default), `search`, `email`, `url`, `tel` or `password`. */
  type?: 'text' | 'search' | 'email' | 'url' | 'tel' | 'password';
  /** Virtual keyboard hint (`decimal` for numbers). */
  inputMode?: 'text' | 'decimal' | 'numeric' | 'search' | 'email' | 'url';
  /** Widget role for composite controls built on Input (Combobox, NumberInput). */
  role?: 'combobox' | 'spinbutton';
  /** Content before the text (an icon or a prefix such as `$`). */
  start?: ReactNode;
  /** Content after the text (a unit such as `%`, a clear button, a chevron). */
  end?: ReactNode;
  /** Text alignment: `end` for numbers. */
  align?: 'start' | 'end';
  /** Monospace text (symbols, feature names, formulas). */
  mono?: boolean;
  /** `md` (density control height, default) or `sm` (inside table rows). */
  size?: 'sm' | 'md';
  /** `auto` (its natural width) or `full` (fill the container, default). */
  width?: 'auto' | 'full';
  /** Canvas-coloured background (search boxes on a surface, per the mockups). */
  sunken?: boolean;
  /** Shows the invalid state (a Field with an error sets this). */
  invalid?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  required?: boolean;
  name?: string;
  id?: string;
  autoComplete?: string;
  spellCheck?: boolean;
  onKeyDown?: KeyboardEventHandler<HTMLInputElement> | undefined;
  onFocus?: FocusEventHandler<HTMLInputElement> | undefined;
  onBlur?: FocusEventHandler<HTMLInputElement> | undefined;
  onClick?: MouseEventHandler<HTMLInputElement> | undefined;
  ref?: Ref<HTMLInputElement>;
}

export function Input({
  value,
  defaultValue,
  onValueChange,
  type = 'text',
  start,
  end,
  align = 'start',
  mono = false,
  size = 'md',
  width = 'full',
  sunken = false,
  invalid = false,
  disabled,
  required,
  id,
  'aria-describedby': describedBy,
  ...rest
}: InputProps) {
  const field = useFieldControl();
  const isInvalid = invalid || Boolean(field?.invalid);
  const isDisabled = disabled ?? field?.disabled ?? false;
  return (
    <div
      className={styles.box}
      data-size={size}
      data-width={width}
      data-sunken={sunken || undefined}
      data-invalid={isInvalid || undefined}
      data-disabled={isDisabled || undefined}
    >
      {start != null && <span className={styles.adornment}>{start}</span>}
      <input
        className={styles.input}
        type={type}
        id={id ?? field?.id}
        value={value}
        defaultValue={defaultValue}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onValueChange?.(event.target.value)}
        data-align={align}
        data-mono={mono || undefined}
        aria-invalid={isInvalid || undefined}
        aria-describedby={joinIds(describedBy, field?.describedBy)}
        disabled={isDisabled}
        required={required ?? field?.required}
        {...rest}
      />
      {end != null && <span className={styles.adornment}>{end}</span>}
    </div>
  );
}
