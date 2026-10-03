/**
 * SegmentedControl: pick exactly one of a few options shown side by side (Hard / Soft,
 * Simple / Pro, 3M / 1Y / 2Y, the workspace switch). A radio group: Tab enters at the selected
 * option, arrow keys (and Home / End) move and select, the selection is shown by an inverted
 * fill, not colour alone. For navigation between pages use NavTabs; for many options, Select.
 */
import { useRef, useState, type KeyboardEvent } from 'react';

import styles from './SegmentedControl.module.css';

export interface SegmentedOption<V extends string = string> {
  value: V;
  label: string;
  /** Longer accessible description (e.g. "Hard: must pass"). */
  description?: string;
  disabled?: boolean;
}

export interface SegmentedControlProps<V extends string = string> {
  /** The choices, in display order (2-5 short labels). */
  options: readonly SegmentedOption<V>[];
  /** The selected value (controlled). */
  value?: V;
  /** The initially selected value (uncontrolled); defaults to the first option. */
  defaultValue?: V;
  /** Called with the newly selected value. */
  onValueChange?: (value: V) => void;
  /** The group's accessible name ("Workspace", "Criterion mode"); required: the options alone do not say what is chosen. */
  'aria-label': string;
  /** `sm` (in table rows: Hard / Soft) or `md` (default: top bar, toolbars). */
  size?: 'sm' | 'md';
  disabled?: boolean;
}

export function SegmentedControl<V extends string = string>({
  options,
  value,
  defaultValue,
  onValueChange,
  'aria-label': ariaLabel,
  size = 'md',
  disabled = false,
}: SegmentedControlProps<V>) {
  const [internal, setInternal] = useState<V | undefined>(defaultValue ?? options[0]?.value);
  const selected = value ?? internal;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const enabled = options.filter((o) => !o.disabled && !disabled);

  const select = (next: V) => {
    if (value === undefined) setInternal(next);
    if (next !== selected) onValueChange?.(next);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, current: V) => {
    const at = enabled.findIndex((o) => o.value === current);
    let target: SegmentedOption<V> | undefined;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown')
      target = enabled[(at + 1) % enabled.length];
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp')
      target = enabled[(at - 1 + enabled.length) % enabled.length];
    else if (event.key === 'Home') target = enabled[0];
    else if (event.key === 'End') target = enabled.at(-1);
    if (!target) return;
    event.preventDefault();
    select(target.value);
    refs.current[options.indexOf(target)]?.focus();
  };

  const tabStop = enabled.some((o) => o.value === selected) ? selected : enabled[0]?.value;

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      aria-disabled={disabled || undefined}
      className={styles.group}
      data-size={size}
    >
      {options.map((option, i) => {
        const checked = option.value === selected;
        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[i] = node;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            title={option.description}
            className={styles.option}
            data-checked={checked || undefined}
            disabled={disabled || option.disabled}
            tabIndex={option.value === tabStop ? 0 : -1}
            onClick={() => {
              select(option.value);
            }}
            onKeyDown={(event) => {
              onKeyDown(event, option.value);
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
