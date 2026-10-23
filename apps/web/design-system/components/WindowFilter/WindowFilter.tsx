/**
 * WindowFilter: "within N days" or "within N sessions" as a number and a unit toggle. Controlled:
 * `value` in, `onChange` out; an empty number means the filter is off. The unit choices and all
 * words are props, so a screen passes its own labels. The number is a `NumberInput` (a
 * spinbutton), the unit a `SegmentedControl` (a radio group).
 */
import { Stack } from '../../primitives/Stack';
import { NumberInput } from '../NumberInput';
import { SegmentedControl, type SegmentedOption } from '../SegmentedControl';
import styles from './WindowFilter.module.css';

export interface WindowValue {
  /** How many units (null: not set). */
  amount: number | null;
  unit: string;
}

export interface WindowFilterProps {
  value: WindowValue;
  onChange: (value: WindowValue) => void;
  /** The units offered, e.g. days and sessions. */
  units: readonly SegmentedOption[];
  /** Accessible name of the number ("Within"). */
  label: string;
  /** Accessible name of the unit toggle ("Unit"). */
  unitLabel: string;
  /** Largest number accepted. */
  max?: number;
}

export function WindowFilter({
  value,
  onChange,
  units,
  label,
  unitLabel,
  max = 365,
}: WindowFilterProps) {
  return (
    <div className={styles.root}>
      <Stack direction="row" gap={2} align="center" wrap>
        <NumberInput
          aria-label={label}
          size="sm"
          width="auto"
          min={0}
          max={max}
          value={value.amount}
          onValueChange={(amount) => {
            onChange({ amount, unit: value.unit });
          }}
        />
        <SegmentedControl
          aria-label={unitLabel}
          size="sm"
          options={units}
          value={value.unit}
          onValueChange={(unit) => {
            onChange({ amount: value.amount, unit });
          }}
        />
      </Stack>
    </div>
  );
}
