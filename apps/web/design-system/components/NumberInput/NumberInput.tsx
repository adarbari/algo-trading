/**
 * NumberInput: a number with an optional unit (`%`, `pts`, `×`) or prefix (`$`), right-aligned
 * in tabular figures. Typing is free (so "1.2" can pass through "1."); the value is parsed,
 * clamped to `min` / `max` and reported on blur or Enter. ArrowUp / ArrowDown step by `step`
 * (Shift: ×10). A spinbutton for screen readers. Empty is `null`, never 0.
 */
import { useState, type KeyboardEvent } from 'react';

import { Input } from '../Input';
import styles from './NumberInput.module.css';

export interface NumberInputProps {
  /** The number (controlled); `null` is empty. */
  value?: number | null;
  /** The initial number (uncontrolled). */
  defaultValue?: number | null;
  /** Called with the parsed, clamped number (or null) on commit: blur, Enter or a step. */
  onValueChange?: (value: number | null) => void;
  /** Lowest allowed value. */
  min?: number;
  /** Highest allowed value. */
  max?: number;
  /** Arrow-key step; 1 by default. */
  step?: number;
  /** Decimal places shown after commit (the step's by default). */
  precision?: number;
  /** A unit after the number ("%", "pts", "sessions"). */
  suffix?: string;
  /** A prefix before the number ("$"). */
  prefix?: string;
  placeholder?: string;
  /** Accessible name outside a Field. */
  'aria-label'?: string;
  /** `md` (default) or `sm` (table rows). */
  size?: 'sm' | 'md';
  /** `full` (default) or `auto` (its natural width, in a row of controls). */
  width?: 'full' | 'auto';
  invalid?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  name?: string;
}

function decimals(step: number): number {
  const text = String(step);
  return text.includes('.') ? (text.split('.')[1]?.length ?? 0) : 0;
}

function parse(text: string): number | null {
  const cleaned = text.replace(/[,\s]/g, '').replace(/^−/, '-');
  if (cleaned === '' || cleaned === '-') return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

export function NumberInput({
  value,
  defaultValue = null,
  onValueChange,
  min,
  max,
  step = 1,
  precision,
  suffix,
  prefix,
  placeholder,
  'aria-label': ariaLabel,
  size = 'md',
  width = 'full',
  invalid = false,
  disabled = false,
  readOnly = false,
  name,
}: NumberInputProps) {
  const places = precision ?? decimals(step);
  const format = (n: number | null): string => (n === null ? '' : n.toFixed(places));
  const [internal, setInternal] = useState<number | null>(defaultValue);
  const current = value === undefined ? internal : value;
  const [draft, setDraft] = useState<string | null>(null);

  const clamp = (n: number): number =>
    Math.min(max ?? Number.POSITIVE_INFINITY, Math.max(min ?? Number.NEGATIVE_INFINITY, n));

  const commit = (next: number | null) => {
    const clamped = next === null ? null : Number(clamp(next).toFixed(places));
    setDraft(null);
    if (value === undefined) setInternal(clamped);
    if (clamped !== current) onValueChange?.(clamped);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (readOnly) return;
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault();
      const base = draft === null ? current : parse(draft);
      const delta = (event.key === 'ArrowUp' ? step : -step) * (event.shiftKey ? 10 : 1);
      commit((base ?? min ?? 0) + (base === null ? 0 : delta));
    } else if (event.key === 'Enter' && draft !== null) {
      commit(parse(draft));
    } else if (event.key === 'Escape' && draft !== null) {
      setDraft(null);
    }
  };

  return (
    <div className={styles.numberInput} data-width={width}>
      <Input
        inputMode="decimal"
        role="spinbutton"
        value={draft ?? format(current)}
        onValueChange={setDraft}
        onKeyDown={onKeyDown}
        onBlur={() => {
          if (draft !== null) commit(parse(draft));
        }}
        aria-label={ariaLabel}
        aria-valuenow={current ?? undefined}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuetext={
          current === null
            ? undefined
            : `${prefix ?? ''}${format(current)}${suffix ? ` ${suffix}` : ''}`
        }
        placeholder={placeholder}
        align="end"
        size={size}
        width={width === 'auto' ? 'auto' : 'full'}
        start={prefix}
        end={suffix}
        invalid={invalid}
        disabled={disabled}
        readOnly={readOnly}
        autoComplete="off"
        {...(name ? { name } : {})}
      />
    </div>
  );
}
