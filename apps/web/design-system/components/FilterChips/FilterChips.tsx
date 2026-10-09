/**
 * FilterChips: the filters of a table as chips. A filter in force is a removable chip
 * ("Screener: VRP scanner", an × named "Remove Screener: VRP scanner"); one not in force is a
 * dashed "+ Name" button that opens its values; "Clear filters" appears only while one is in
 * force. The row wraps, so it fits a phone. The caller owns the values (usually search params)
 * and what each filter means; this only shows and edits them.
 */
import { useState } from 'react';

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

export interface FilterChipsProps {
  filters: readonly FilterDefinition[];
  values: FilterValues;
  /** Set a filter's value, or remove it (`undefined`). */
  onChange: (id: string, value: string | undefined) => void;
  /** Remove every filter in force. */
  onClear: () => void;
}

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

export function FilterChips({ filters, values, onChange, onClear }: FilterChipsProps) {
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
