/**
 * Select: pick one value from a short, known list (expiry, sort order, preset). The native
 * select, styled with tokens: full keyboard, screen-reader and mobile support for free. For long
 * or searchable lists with descriptions use Combobox; for 2-4 visible options, SegmentedControl.
 */
import type { ChangeEvent } from 'react';

import { joinIds, useFieldControl } from '../Field';
import { Icon } from '../Icon';
import styles from './Select.module.css';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
  /** Options with the same group are shown under that heading. */
  group?: string;
}

export interface SelectProps {
  /** The choices, in display order. */
  options: readonly SelectOption[];
  /** The selected value (controlled). */
  value?: string;
  /** The initial value (uncontrolled). */
  defaultValue?: string;
  /** Called with the chosen value. */
  onValueChange?: (value: string) => void;
  /** A first, unselectable prompt ("Choose an expiry"); selected while no value is set. */
  placeholder?: string;
  /** Accessible name outside a Field. */
  'aria-label'?: string;
  /** `md` (default) or `sm`. */
  size?: 'sm' | 'md';
  /** `full` (default) or `auto`. */
  width?: 'full' | 'auto';
  invalid?: boolean;
  disabled?: boolean;
  required?: boolean;
  name?: string;
  id?: string;
}

function grouped(options: readonly SelectOption[]): [string | undefined, SelectOption[]][] {
  const groups: [string | undefined, SelectOption[]][] = [];
  for (const option of options) {
    const last = groups.at(-1);
    if (last && last[0] === option.group) last[1].push(option);
    else groups.push([option.group, [option]]);
  }
  return groups;
}

export function Select({
  options,
  value,
  defaultValue,
  onValueChange,
  placeholder,
  'aria-label': ariaLabel,
  size = 'md',
  width = 'full',
  invalid = false,
  disabled,
  required,
  name,
  id,
}: SelectProps) {
  const field = useFieldControl();
  const isInvalid = invalid || Boolean(field?.invalid);
  const isDisabled = disabled ?? field?.disabled ?? false;
  const renderOption = (o: SelectOption) => (
    <option key={o.value} value={o.value} disabled={o.disabled}>
      {o.label}
    </option>
  );
  return (
    <div
      className={styles.box}
      data-size={size}
      data-width={width}
      data-invalid={isInvalid || undefined}
      data-disabled={isDisabled || undefined}
    >
      <select
        className={styles.select}
        id={id ?? field?.id}
        name={name}
        value={value}
        defaultValue={
          value === undefined ? (defaultValue ?? (placeholder ? '' : undefined)) : undefined
        }
        onChange={(event: ChangeEvent<HTMLSelectElement>) => onValueChange?.(event.target.value)}
        aria-label={ariaLabel}
        aria-invalid={isInvalid || undefined}
        aria-describedby={joinIds(field?.describedBy)}
        disabled={isDisabled}
        required={required ?? field?.required}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {grouped(options).map(([group, items]) =>
          group ? (
            <optgroup key={group} label={group}>
              {items.map(renderOption)}
            </optgroup>
          ) : (
            items.map(renderOption)
          ),
        )}
      </select>
      <span className={styles.chevron}>
        <Icon name="chevron-down" />
      </span>
    </div>
  );
}
