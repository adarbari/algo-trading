/**
 * FilterChips: the filters of a table as chips. A filter in force is a removable chip
 * ("Screener: VRP scanner", an × named "Remove Screener: VRP scanner"); one not in force is a
 * dashed "+ Name" button that opens its values; "Clear filters" appears only while one is in
 * force. The row wraps, so it fits a phone. The caller owns the values (usually search params)
 * and what each filter means; this only shows and edits them.
 * Structured form (`items`, ADR 0082): each applied filter is a toggle button ("Label value",
 * `aria-pressed`, struck through and marked "off" while switched off) with its server-counted
 * "removes N" and "N unknown", and a remove button; after a removal focus moves to the next
 * chip. The two forms are one discriminated union: `items` selects the structured one.
 */
import { useEffect, useRef, useState, type RefObject } from 'react';

import { formatValue } from '../../format';

import { Stack } from '../../primitives/Stack';
import { Button } from '../Button';
import { Chip } from '../Chip';
import { OptionList } from '../OptionList';
import { Popover } from '../Popover';
import styles from './FilterChips.module.css';

export interface FilterDefinition {
  /** Stable key of the filter (the key of its value in `values`). */
  id: string;
  /** The filter's name ("Screener"). */
  label: string;
  /** The values it offers. */
  options: readonly { value: string; label: string }[];
}

/** The value in force per filter id; absent or undefined: not in force. */
export type FilterValues = Readonly<Record<string, string | undefined>>;

export interface LegacyFilterChipsProps {
  filters: readonly FilterDefinition[];
  values: FilterValues;
  /** Set a filter's value, or remove it (`undefined`). */
  onChange: (id: string, value: string | undefined) => void;
  /** Remove every filter in force. */
  onClear: () => void;
  items?: never;
}

export interface FilterChipItem {
  /** Stable key of the filter. */
  id: string;
  /** The filter's name ("Decision"). */
  label: string;
  /** Its value as text ("Qualified, Watch", "30 to 70"). */
  valueText: string;
  /** Rows this filter removes given the others (server-counted). */
  removes?: number;
  /** Rows with no value for it (they never pass). */
  unknown?: number;
  /** False: switched off (kept, in no mask). */
  active: boolean;
}

export interface StructuredFilterChipsProps {
  items: readonly FilterChipItem[];
  /** Switch a chip off or on. */
  onToggle: (id: string) => void;
  /** Remove a chip. */
  onRemove: (id: string) => void;
  /** Remove every chip; the button is drawn only when passed (else `FilterBar.actions` owns it). */
  onClear?: () => void;
  /** Where focus goes when the last chip goes (the search input); else the chip row itself. */
  emptyFocusRef?: RefObject<HTMLElement | null>;
  /** The word before the removed count (default "removes"). */
  removesLabel?: string;
  /** The word after the unknown count (default "unknown"). */
  unknownLabel?: string;
  /** The word marking a switched-off chip (default "off"). */
  offLabel?: string;
  /** Text of the clear button (default "Clear all"). */
  clearLabel?: string;
  /** Accessible name of the row (default "Applied filters"). */
  label?: string;
  filters?: never;
}

export type FilterChipsProps = LegacyFilterChipsProps | StructuredFilterChipsProps;

function AddFilter({
  filter,
  onPick,
}: {
  filter: FilterDefinition;
  onPick: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      label={filter.label}
      open={open}
      onOpenChange={setOpen}
      padding="none"
      trigger={(props) => (
        <Button {...props} variant="dashed" size="sm" icon="plus">
          {filter.label}
        </Button>
      )}
    >
      <OptionList
        label={filter.label}
        value={null}
        maxHeight="md"
        items={filter.options.map((o) => ({ id: o.value, title: o.label }))}
        onSelect={(value) => {
          onPick(value);
          setOpen(false);
        }}
      />
    </Popover>
  );
}

function StructuredChips({
  items,
  onToggle,
  onRemove,
  onClear,
  emptyFocusRef,
  removesLabel = 'removes',
  unknownLabel = 'unknown',
  offLabel = 'off',
  clearLabel = 'Clear all',
  label = 'Applied filters',
}: StructuredFilterChipsProps) {
  const toggles = useRef<(HTMLButtonElement | null)[]>([]);
  const group = useRef<HTMLDivElement | null>(null);
  const focusAfter = useRef<number | null>(null);
  useEffect(() => {
    if (focusAfter.current === null) return;
    if (items.length === 0) (emptyFocusRef?.current ?? group.current)?.focus();
    else toggles.current[Math.min(focusAfter.current, items.length - 1)]?.focus();
    focusAfter.current = null;
  }, [items.length, emptyFocusRef]);
  const count = (n: number) => formatValue(n, { kind: 'number' }).text;
  const metaOf = (item: FilterChipItem): string | undefined => {
    const parts = [
      ...(item.active ? [] : [offLabel]),
      ...(item.active && item.removes !== undefined
        ? [`${removesLabel} ${count(item.removes)}`]
        : []),
      ...(item.unknown !== undefined && item.unknown > 0
        ? [`${count(item.unknown)} ${unknownLabel}`]
        : []),
    ];
    return parts.length > 0 ? parts.join(' · ') : undefined;
  };
  return (
    <div ref={group} className={styles.root} role="group" aria-label={label} tabIndex={-1}>
      <Stack direction="row" gap={1} align="center" wrap>
        {items.map((item, index) => {
          const meta = metaOf(item);
          return (
            <Chip
              key={item.id}
              label={`${item.label} ${item.valueText}`}
              selected={item.active}
              struck={!item.active}
              {...(meta !== undefined && { meta })}
              buttonRef={(node) => {
                toggles.current[index] = node;
              }}
              onSelectedChange={() => {
                onToggle(item.id);
              }}
              onRemove={() => {
                focusAfter.current = index;
                onRemove(item.id);
              }}
            />
          );
        })}
        {items.length > 0 && onClear ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              focusAfter.current = 0;
              onClear();
            }}
          >
            {clearLabel}
          </Button>
        ) : null}
      </Stack>
    </div>
  );
}

function LegacyChips({ filters, values, onChange, onClear }: LegacyFilterChipsProps) {
  const inForce = filters.filter((f) => values[f.id] !== undefined);
  const free = filters.filter((f) => values[f.id] === undefined);
  return (
    <div className={styles.root}>
      <Stack direction="row" gap={1} align="center" wrap>
        {inForce.map((filter) => {
          const value = values[filter.id] ?? '';
          const label = filter.options.find((o) => o.value === value)?.label ?? value;
          return (
            <Chip
              key={filter.id}
              label={`${filter.label}: ${label}`}
              onRemove={() => {
                onChange(filter.id, undefined);
              }}
            />
          );
        })}
        {free.map((filter) => (
          <AddFilter
            key={filter.id}
            filter={filter}
            onPick={(value) => {
              onChange(filter.id, value);
            }}
          />
        ))}
        {inForce.length > 0 ? (
          <Button size="sm" variant="ghost" onClick={onClear}>
            Clear filters
          </Button>
        ) : null}
      </Stack>
    </div>
  );
}

export function FilterChips(props: FilterChipsProps) {
  return props.items === undefined ? <LegacyChips {...props} /> : <StructuredChips {...props} />;
}
