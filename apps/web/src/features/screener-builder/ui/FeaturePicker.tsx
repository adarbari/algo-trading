/**
 * The feature picker: the catalogue as a searchable Combobox, each option with its description,
 * unit and licence, grouped by feature group; the user's own formulas are badged.
 */
import { Combobox, type ComboboxOption } from '@algotrade/ui';
import { useMemo } from 'react';

import {
  featureGroup,
  featureLabel,
  isOwn,
  isPersonal,
  unitLabel,
  type CatalogueFeature,
} from '@/entities/feature';

export function featureOptions(catalogue: readonly CatalogueFeature[]): ComboboxOption[] {
  return catalogue.map((feature) => {
    const parts = [feature.description, unitLabel(feature.unit)];
    if (isPersonal(feature)) parts.push('personal licence');
    const badge = isOwn(feature) ? 'yours' : feature.name.startsWith('feature.') ? 'formula' : null;
    return {
      value: feature.name,
      label: feature.name,
      // The closed input reads as a name, not the long dotted id (that is its tooltip).
      inputLabel: featureLabel(feature.name),
      description: parts.filter(Boolean).join(' · '),
      ...(badge ? { badge } : {}),
      group: featureGroup(feature),
    };
  });
}

export interface FeaturePickerProps {
  catalogue: readonly CatalogueFeature[];
  loading?: boolean;
  value: string | null;
  onChange: (field: string) => void;
  invalid?: boolean;
  disabled?: boolean;
}

export function FeaturePicker({
  catalogue,
  loading = false,
  value,
  onChange,
  invalid = false,
  disabled = false,
}: FeaturePickerProps) {
  const options = useMemo(() => featureOptions(catalogue), [catalogue]);
  return (
    <Combobox
      aria-label="Feature or formula"
      size="sm"
      mono
      options={options}
      value={value || null}
      loading={loading}
      placeholder="Choose a feature…"
      emptyMessage="No feature matches"
      onValueChange={(next) => {
        if (next) onChange(next);
      }}
      invalid={invalid}
      disabled={disabled}
    />
  );
}
