/**
 * The column that sorts rows with equal scores (`[rank] tie_break`): a numeric feature, high or
 * low first. One a preset sets can be changed or cleared in a copy.
 */
import { Button, SegmentedControl, Stack, Text } from '@algotrade/ui';
import { useMemo } from 'react';

import {
  FeatureCombobox,
  fieldOptions,
  isNumericFeature,
  type CatalogueFeature,
} from '@/entities/feature';

export interface TieBreakFieldProps {
  catalogue: readonly CatalogueFeature[];
  field: string | null;
  order: 'asc' | 'desc';
  onChange: (field: string | null, order: 'asc' | 'desc') => void;
  disabled?: boolean;
}

const ORDER = [
  { value: 'desc', label: 'High first' },
  { value: 'asc', label: 'Low first' },
];

export function TieBreakField({
  catalogue,
  field,
  order,
  onChange,
  disabled = false,
}: TieBreakFieldProps) {
  const options = useMemo(() => fieldOptions(catalogue.filter(isNumericFeature)), [catalogue]);
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      <Text size="sm" tone="secondary">
        Tie-break on
      </Text>
      <FeatureCombobox
        aria-label="Feature or formula"
        size="sm"
        mono
        options={options}
        value={field}
        placeholder="Choose a feature…"
        onPick={(next) => {
          onChange(next, order);
        }}
        disabled={disabled}
      />
      <SegmentedControl
        aria-label="Tie-break order"
        size="sm"
        options={ORDER}
        value={order}
        onValueChange={(next) => {
          if (field) onChange(field, next === 'asc' ? 'asc' : 'desc');
        }}
        disabled={disabled || !field}
      />
      {field && (
        <Button
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={() => {
            onChange(null, order);
          }}
        >
          Clear tie-break
        </Button>
      )}
    </Stack>
  );
}
