/** The column that sorts rows with equal scores (`[rank] tie_break`): a numeric feature, high or low first. */
import { SegmentedControl, Stack, Text } from '@algotrade/ui';

import { isNumericFeature, type CatalogueFeature } from '@/entities/feature';

import { FeaturePicker } from './FeaturePicker';

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
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      <Text size="sm" tone="secondary">
        Tie-break on
      </Text>
      <FeaturePicker
        catalogue={catalogue.filter(isNumericFeature)}
        value={field}
        onChange={(next) => {
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
    </Stack>
  );
}
