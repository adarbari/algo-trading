/**
 * Combobox: choose one value from a long or searchable list by typing (the feature picker).
 * Each option shows a label (mono for feature names), an optional kind badge ("formula") and a
 * secondary description, grouped under headings. Filters locally, or asynchronously: pass
 * `filter="none"`, fetch on `onInputChange`, and set `options` and `loading`. Keyboard per the
 * ARIA combobox pattern: ArrowDown / ArrowUp open and move, Enter selects, Escape closes, Tab
 * leaves; the active option is announced through aria-activedescendant.
 */
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';

import { Text } from '../../primitives/Text';
import { useFieldControl } from '../Field';
import { Icon } from '../Icon';
import { Input } from '../Input';
import styles from './Combobox.module.css';

export interface ComboboxOption {
  value: string;
  /** The main text ("iv30@v1.iv30"). */
  label: string;
  /** What the closed input shows once this option is chosen, when the label is too technical or
   * too long for it ("Last close" for "rollup.price_stats@v2.close"); the full label is the
   * input's tooltip. Default: the label. */
  inputLabel?: string;
  /** Secondary text under the label ("Our 30-day ATM implied volatility"). */
  description?: string;
  /** A short kind badge ("formula", "catalogue", "ETF"). */
  badge?: string;
  /** Options with the same group are listed under that heading. */
  group?: string;
  disabled?: boolean;
}

export interface ComboboxProps {
  /** The options (all of them, or the caller's async results with `filter="none"`). */
  options: readonly ComboboxOption[];
  /** The selected value (controlled); null is none. */
  value?: string | null;
  /** The initially selected value (uncontrolled). */
  defaultValue?: string | null;
  /** Called with the chosen value and its option. */
  onValueChange?: (value: string | null, option: ComboboxOption | null) => void;
  /** Called with the typed query (fetch async options here). */
  onInputChange?: (query: string) => void;
  /** `contains` (default): match label, description and badge locally; `none`: options are already filtered. */
  filter?: 'contains' | 'none';
  /** Options are being fetched. */
  loading?: boolean;
  /** Options failed to load: the message shown in the list. */
  error?: string;
  /** Shown when nothing matches. */
  emptyMessage?: string;
  placeholder?: string;
  /** Accessible name outside a Field. */
  'aria-label'?: string;
  /** Option labels and the text in monospace (feature names, symbols). */
  mono?: boolean;
  /** `md` (default) or `sm` (table rows). */
  size?: 'sm' | 'md';
  invalid?: boolean;
  disabled?: boolean;
  name?: string;
}

function matches(option: ComboboxOption, query: string): boolean {
  const q = query.trim().toLowerCase();
  return [option.label, option.description, option.badge].some((t) => t?.toLowerCase().includes(q));
}

/** Options ordered by group (groups in order of first appearance), stable within a group. */
function byGroup(options: readonly ComboboxOption[]): ComboboxOption[] {
  const groups = [...new Set(options.map((o) => o.group))];
  return groups.flatMap((g) => options.filter((o) => o.group === g));
}

export function Combobox({
  options,
  value,
  defaultValue = null,
  onValueChange,
  onInputChange,
  filter = 'contains',
  loading = false,
  error,
  emptyMessage = 'No matches',
  placeholder,
  'aria-label': ariaLabel,
  mono = false,
  size = 'md',
  invalid = false,
  disabled = false,
  name,
}: ComboboxProps) {
  const field = useFieldControl();
  const baseId = useId();
  const listId = `${baseId}list`;
  const [internal, setInternal] = useState<string | null>(defaultValue);
  const selectedValue = value === undefined ? internal : value;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const [known, setKnown] = useState<ComboboxOption | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const selected =
    options.find((o) => o.value === selectedValue) ??
    (known?.value === selectedValue ? known : null);
  const shown = useMemo(
    () =>
      byGroup(filter === 'contains' && query ? options.filter((o) => matches(o, query)) : options),
    [options, filter, query],
  );
  const enabled = shown.map((o, i) => (o.disabled ? -1 : i)).filter((i) => i >= 0);
  const optionId = (i: number) => `${baseId}opt${i}`;

  useEffect(() => {
    if (open && active >= 0) {
      listRef.current
        ?.querySelector(`[data-index="${String(active)}"]`)
        ?.scrollIntoView({ block: 'nearest' });
    }
  }, [open, active]);

  const openAt = (index: number) => {
    setOpen(true);
    setActive(index);
  };
  const close = () => {
    setOpen(false);
    setQuery(null);
    setActive(-1);
  };
  const choose = (option: ComboboxOption) => {
    if (option.disabled) return;
    setKnown(option);
    if (value === undefined) setInternal(option.value);
    if (option.value !== selectedValue) onValueChange?.(option.value, option);
    close();
  };
  const step = (delta: 1 | -1) => {
    if (enabled.length === 0) return;
    const at = enabled.indexOf(active);
    const next =
      at < 0
        ? delta === 1
          ? enabled[0]
          : enabled.at(-1)
        : enabled[(at + delta + enabled.length) % enabled.length];
    setActive(next ?? -1);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        const current = shown.findIndex((o) => o.value === selectedValue);
        openAt(
          current >= 0
            ? current
            : ((event.key === 'ArrowDown' ? enabled[0] : enabled.at(-1)) ?? -1),
        );
      } else step(event.key === 'ArrowDown' ? 1 : -1);
    } else if (event.key === 'Enter' && open) {
      event.preventDefault();
      const option = shown[active];
      if (option) choose(option);
    } else if (event.key === 'Escape' && open) {
      event.preventDefault();
      close();
    } else if (event.key === 'Tab') {
      close();
    }
  };

  const status = loading ? 'Loading…' : error ? error : shown.length === 0 ? emptyMessage : null;

  // Options are never focused: the input keeps focus and points at the active option with
  // aria-activedescendant (ARIA combobox pattern), so keyboard handling lives on the input.
  const renderOption = (option: ComboboxOption, i: number) => (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/interactive-supports-focus
    <div
      key={option.value}
      id={optionId(i)}
      role="option"
      aria-selected={option.value === selectedValue}
      aria-disabled={option.disabled || undefined}
      data-index={i}
      data-active={i === active || undefined}
      className={styles.option}
      onMouseDown={(event) => {
        event.preventDefault();
      }}
      onMouseMove={() => {
        if (!option.disabled && i !== active) setActive(i);
      }}
      onClick={() => {
        choose(option);
      }}
    >
      <span className={styles.optionMain}>
        <span className={styles.optionLabel} data-mono={mono || undefined}>
          {option.label}
        </span>
        {option.badge && <span className={styles.badge}>{option.badge}</span>}
        {option.value === selectedValue && <Icon name="check" size="sm" tone="accent" />}
      </span>
      {option.description && (
        <Text size="xs" tone="muted">
          {option.description}
        </Text>
      )}
    </div>
  );

  const sections = sectionsOf(shown);

  return (
    <div
      className={styles.combobox}
      title={selected?.inputLabel && query === null ? selected.label : undefined}
    >
      <Input
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
        value={query ?? selected?.inputLabel ?? selected?.label ?? ''}
        onValueChange={(text) => {
          setQuery(text);
          setOpen(true);
          setActive(-1);
          onInputChange?.(text);
        }}
        onKeyDown={onKeyDown}
        onClick={() => {
          if (open) close();
          else openAt(shown.findIndex((o) => o.value === selectedValue));
        }}
        onBlur={close}
        placeholder={placeholder}
        mono={mono && (query !== null || !selected?.inputLabel)}
        size={size}
        invalid={invalid}
        disabled={disabled}
        autoComplete="off"
        spellCheck={false}
        end={<Icon name={open ? 'chevron-up' : 'chevron-down'} />}
        {...(name ? { name } : {})}
      />
      {open && (
        <div className={styles.popover}>
          <div
            ref={listRef}
            id={listId}
            role="listbox"
            className={styles.list}
            aria-busy={loading || undefined}
            {...(field
              ? { 'aria-labelledby': field.labelId }
              : { 'aria-label': ariaLabel ?? 'Options' })}
          >
            {sections.map(({ group, items }, g) =>
              group === undefined ? (
                items.map(({ option, index }) => renderOption(option, index))
              ) : (
                <div
                  key={group}
                  role="group"
                  aria-labelledby={`${baseId}group${g}`}
                  className={styles.group}
                >
                  <div id={`${baseId}group${g}`} className={styles.groupLabel}>
                    {group}
                  </div>
                  {items.map(({ option, index }) => renderOption(option, index))}
                </div>
              ),
            )}
          </div>
          {status && (
            <div role="status" className={styles.status} data-error={error ? true : undefined}>
              {loading && <Icon name="spinner" spin size="sm" />}
              {error && !loading && <Icon name="alert" size="sm" tone="negative" />}
              <Text size="sm" tone={error && !loading ? 'negative' : 'muted'}>
                {status}
              </Text>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface Section {
  group: string | undefined;
  items: { option: ComboboxOption; index: number }[];
}

/** Consecutive options of one group (shown is already ordered by group). */
function sectionsOf(shown: readonly ComboboxOption[]): Section[] {
  const sections: Section[] = [];
  shown.forEach((option, index) => {
    const last = sections.at(-1);
    if (last && last.group === option.group) last.items.push({ option, index });
    else sections.push({ group: option.group, items: [{ option, index }] });
  });
  return sections;
}
