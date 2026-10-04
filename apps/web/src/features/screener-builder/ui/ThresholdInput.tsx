/**
 * The threshold of a criterion, in the control its operator and field type call for: a number
 * in the field's unit (a fraction typed as a percent), a range, a list ("HIGH, LOW"), a
 * Yes / No choice or text. Nothing for "is empty" / "has a value".
 */
import { Input, NumberInput, Select, Stack, Text } from '@algotrade/ui';
import { useState } from 'react';

import type { CatalogueFeature } from '@/entities/feature';

import {
  fieldKind,
  parseList,
  scaleOf,
  shapeOf,
  toStored,
  toTyped,
  type FieldKind,
  type NumberScale,
} from '../model/threshold';

export interface ThresholdInputProps {
  feature: CatalogueFeature | undefined;
  op: string;
  value: unknown;
  onChange: (value: unknown) => void;
  invalid?: boolean;
  disabled?: boolean;
}

const YES_NO = [
  { value: 'true', label: 'Yes' },
  { value: 'false', label: 'No' },
];

function NumberField({
  value,
  scale,
  label,
  invalid,
  disabled,
  onChange,
}: {
  value: unknown;
  scale: NumberScale;
  label: string;
  invalid: boolean;
  disabled: boolean;
  onChange: (value: number | null) => void;
}) {
  return (
    <NumberInput
      aria-label={label}
      size="sm"
      width="auto"
      value={typeof value === 'number' ? toTyped(value, scale) : null}
      onValueChange={(typed) => {
        onChange(typed === null ? null : toStored(typed, scale));
      }}
      {...(scale.prefix ? { prefix: scale.prefix } : {})}
      {...(scale.suffix ? { suffix: scale.suffix } : {})}
      {...(scale.factor === 100 ? { precision: 1 } : {})}
      step={scale.step}
      invalid={invalid}
      disabled={disabled}
    />
  );
}

/** A list typed as text; committed on blur or Enter so a trailing comma survives typing. */
function ListField({
  value,
  kind,
  invalid,
  disabled,
  onChange,
}: {
  value: unknown;
  kind: FieldKind;
  invalid: boolean;
  disabled: boolean;
  onChange: (value: unknown) => void;
}) {
  const shown = Array.isArray(value) ? value.join(', ') : '';
  const [text, setText] = useState<string | null>(null);
  const commit = () => {
    if (text !== null) onChange(parseList(text, kind));
    setText(null);
  };
  return (
    <Input
      aria-label="Values, separated by commas"
      size="sm"
      width="auto"
      value={text ?? shown}
      placeholder="HIGH, LOW"
      onValueChange={setText}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') commit();
      }}
      invalid={invalid}
      disabled={disabled}
    />
  );
}

export function ThresholdInput({
  feature,
  op,
  value,
  onChange,
  invalid = false,
  disabled = false,
}: ThresholdInputProps) {
  const kind = fieldKind(feature);
  const shape = shapeOf(op);
  const scale = scaleOf(feature);
  if (shape === 'none') {
    return (
      <Text size="sm" tone="muted">
        no threshold
      </Text>
    );
  }
  if (shape === 'list') {
    return (
      <ListField
        value={value}
        kind={kind}
        invalid={invalid}
        disabled={disabled}
        onChange={onChange}
      />
    );
  }
  if (shape === 'range') {
    const [low, high] = Array.isArray(value) ? (value as unknown[]) : [null, null];
    const set = (index: 0 | 1) => (next: number | null) => {
      const pair: (number | null)[] = [
        typeof low === 'number' ? low : null,
        typeof high === 'number' ? high : null,
      ];
      pair[index] = next;
      onChange(pair[0] === null || pair[1] === null ? undefined : pair);
    };
    return (
      <Stack direction="row" gap={1} align="center">
        <NumberField
          label="From"
          value={low}
          scale={scale}
          invalid={invalid}
          disabled={disabled}
          onChange={set(0)}
        />
        <Text size="sm" tone="muted">
          and
        </Text>
        <NumberField
          label="To"
          value={high}
          scale={scale}
          invalid={invalid}
          disabled={disabled}
          onChange={set(1)}
        />
      </Stack>
    );
  }
  if (kind === 'number') {
    return (
      <NumberField
        label="Threshold"
        value={value}
        scale={scale}
        invalid={invalid}
        disabled={disabled}
        onChange={(n) => {
          onChange(n ?? undefined);
        }}
      />
    );
  }
  if (kind === 'bool') {
    return (
      <Select
        aria-label="Threshold"
        size="sm"
        width="auto"
        options={YES_NO}
        value={value === false ? 'false' : 'true'}
        onValueChange={(next) => {
          onChange(next === 'true');
        }}
        disabled={disabled}
      />
    );
  }
  const categories = feature?.categories ?? [];
  if (kind === 'text' && categories.length > 0) {
    return (
      <Select
        aria-label="Threshold"
        size="sm"
        width="auto"
        placeholder="Choose a value"
        options={categories.map((c) => ({ value: c, label: c }))}
        value={typeof value === 'string' ? value : ''}
        onValueChange={onChange}
        invalid={invalid}
        disabled={disabled}
      />
    );
  }
  return (
    <Input
      aria-label="Threshold"
      size="sm"
      width="auto"
      value={typeof value === 'string' ? value : ''}
      placeholder={kind === 'date' ? 'YYYY-MM-DD' : 'value'}
      onValueChange={(text) => {
        onChange(text === '' ? undefined : text);
      }}
      invalid={invalid}
      disabled={disabled}
    />
  );
}
