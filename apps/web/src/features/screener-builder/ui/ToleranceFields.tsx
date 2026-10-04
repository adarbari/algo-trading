/**
 * How far a soft (or score) criterion may miss its threshold and still count as a near miss: an
 * amount in the field's unit, or a share of the threshold; for a soft one, the decision a near
 * miss gives (WATCH, LIQUIDITY_RISK, EVENT_RISK).
 */
import { NumberInput, Select, Stack, Text } from '@algotrade/ui';

import {
  MISS_DECISIONS,
  type Criterion,
  type MissDecision,
  type Tolerance,
} from '@/entities/screen';
import type { CatalogueFeature } from '@/entities/feature';

import { scaleOf, toStored, toTyped, type ToleranceUnit } from '../model/threshold';

const UNITS = [
  { value: 'absolute', label: 'amount' },
  { value: 'relative', label: '% of threshold' },
];
const MISSES = MISS_DECISIONS.map((value) => ({
  value,
  label: value.replace('_', ' ').toLowerCase(),
}));

const unitOf = (tolerance: Tolerance | undefined): ToleranceUnit =>
  typeof tolerance === 'object' ? 'relative' : 'absolute';

export interface ToleranceFieldsProps {
  criterion: Criterion;
  feature: CatalogueFeature | undefined;
  onChange: (criterion: Criterion) => void;
  invalid?: boolean;
  disabled?: boolean;
}

export function ToleranceFields({
  criterion,
  feature,
  onChange,
  invalid = false,
  disabled = false,
}: ToleranceFieldsProps) {
  const scale = scaleOf(feature);
  const { tolerance } = criterion;
  const unit = unitOf(tolerance);
  const typed =
    tolerance === undefined
      ? null
      : typeof tolerance === 'object'
        ? tolerance.relative * 100
        : toTyped(tolerance, scale);
  const set = (next: Tolerance | undefined) => {
    onChange({ ...criterion, tolerance: next });
  };
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      <Text size="sm" tone="secondary">
        Tolerance
      </Text>
      <NumberInput
        aria-label="Tolerance"
        size="sm"
        width="auto"
        value={typed}
        min={0}
        {...(unit === 'absolute' && scale.prefix ? { prefix: scale.prefix } : {})}
        {...(unit === 'absolute'
          ? scale.suffix
            ? { suffix: scale.suffix }
            : {}
          : { suffix: '%' })}
        {...(unit === 'relative' || scale.factor === 100 ? { precision: 1 } : {})}
        step={unit === 'absolute' ? scale.step : 5}
        onValueChange={(next) => {
          if (next === null) set(undefined);
          else set(unit === 'relative' ? { relative: next / 100 } : toStored(next, scale));
        }}
        invalid={invalid}
        disabled={disabled}
      />
      <Select
        aria-label="Tolerance unit"
        size="sm"
        width="auto"
        options={UNITS}
        value={unit}
        onValueChange={(next) => {
          if (next === unit || typed === null) return;
          set(next === 'relative' ? { relative: 0.1 } : toStored(typed, scale));
        }}
        disabled={disabled}
      />
      {criterion.mode === 'soft' && (
        <>
          <Text size="sm" tone="secondary">
            A near miss is
          </Text>
          <Select
            aria-label="Decision for a near miss"
            size="sm"
            width="auto"
            options={MISSES}
            value={criterion.on_miss ?? 'WATCH'}
            onValueChange={(next) => {
              onChange({ ...criterion, on_miss: next as MissDecision });
            }}
            disabled={disabled}
          />
        </>
      )}
    </Stack>
  );
}
