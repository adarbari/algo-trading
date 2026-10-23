/**
 * RangeFilter: a numeric filter as a minimum and a maximum (two `NumberInput`s, either may be
 * empty for an open end) with a unit, and optionally a histogram of the candidates (`bins`,
 * drawn by `Distribution`, decorative: its counts are also given as text for screen readers).
 * No slider. `unknownCount` says how many rows have no value, who never pass the filter.
 * Controlled: `value` in, `onChange` out. All words are props.
 */
import type { ReactNode } from 'react';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { formatValue } from '../../format';
import { describeDistribution, Distribution, type DistributionBin } from '../Distribution';
import { NumberInput } from '../NumberInput';
import styles from './RangeFilter.module.css';

export interface RangeValue {
  min?: number;
  max?: number;
}

export interface RangeFilterProps {
  value: RangeValue;
  onChange: (value: RangeValue) => void;
  /** Accessible name of the pair and the histogram ("DTE"). */
  label: string;
  /** Accessible name of the minimum (default "Min"). */
  minLabel?: string;
  /** Accessible name of the maximum (default "Max"). */
  maxLabel?: string;
  /** A unit shown after each number ("%", "days"). */
  unit?: string;
  /** Arrow-key step (default 1). */
  step?: number;
  /** The lowest and highest value either end accepts (clamped by the number fields). */
  bounds?: { min: number; max: number };
  /** Fixed-edge histogram of the candidates; counts also given as text. */
  bins?: readonly DistributionBin[];
  /** How many rows have no value (they never pass). */
  unknownCount?: number;
  /** The word before the unknown count (default "Unknown"). */
  unknownLabel?: string;
  /** Beside the unknown count: the caller's `InfoButton` for its Guide term. */
  unknownHelp?: ReactNode;
}

export function RangeFilter({
  value,
  onChange,
  label,
  minLabel = 'Min',
  maxLabel = 'Max',
  unit,
  step = 1,
  bins,
  unknownCount,
  unknownLabel = 'Unknown',
  unknownHelp,
  bounds,
}: RangeFilterProps) {
  const hasBins = bins !== undefined && bins.length > 0;
  const set = (key: 'min' | 'max', n: number | null) => {
    const lo = key === 'min' ? (n ?? undefined) : value.min;
    const hi = key === 'max' ? (n ?? undefined) : value.max;
    // Reversed ends (min above max) are swapped, never reported.
    const [a, b] = lo !== undefined && hi !== undefined && lo > hi ? [hi, lo] : [lo, hi];
    const next: RangeValue = {};
    if (a !== undefined) next.min = a;
    if (b !== undefined) next.max = b;
    onChange(next);
  };
  return (
    <div className={styles.root} role="group" aria-label={label}>
      <Stack gap={2}>
        {hasBins && (
          <>
            <div aria-hidden="true">
              <Distribution bins={bins} label={label} height="sm" />
            </div>
            <VisuallyHidden>
              {describeDistribution(label, bins, [], { kind: 'number' })}
            </VisuallyHidden>
          </>
        )}
        <Stack direction="row" gap={2} align="center">
          <div className={styles.field}>
            <NumberInput
              aria-label={minLabel}
              size="sm"
              step={step}
              {...(bounds && { min: bounds.min, max: bounds.max })}
              {...(unit !== undefined && { suffix: unit })}
              value={value.min ?? null}
              onValueChange={(n) => {
                set('min', n);
              }}
            />
          </div>
          <div className={styles.field}>
            <NumberInput
              aria-label={maxLabel}
              size="sm"
              step={step}
              {...(bounds && { min: bounds.min, max: bounds.max })}
              {...(unit !== undefined && { suffix: unit })}
              value={value.max ?? null}
              onValueChange={(n) => {
                set('max', n);
              }}
            />
          </div>
        </Stack>
        {unknownCount !== undefined && unknownCount > 0 && (
          <Stack direction="row" gap={1} align="center">
            <Text size="sm" tone="muted">
              {`${unknownLabel}: ${formatValue(unknownCount, { kind: 'number' }).text}`}
            </Text>
            {unknownHelp}
          </Stack>
        )}
      </Stack>
    </div>
  );
}
