/**
 * Pick features from the catalogue (the ticker table's columns, the compare table's
 * dimensions): a popover with a searchable Combobox, each option showing the feature's name,
 * description, unit and kind (the user's own features marked personal), and the chosen ones
 * as removable chips. Controlled: the caller keeps the list (in the URL).
 */
import { Button, Chip, Combobox, Field, Popover, Stack, Text, type IconName } from '@algotrade/ui';
import { useMemo } from 'react';

import { byName, featureLabel, featureMarks, useFeatureCatalogue } from '@/entities/feature';

import { featureOptions } from '../model/options';

export interface FeaturePickerProps {
  /** The trigger's text and the popover's name ("Columns", "Dimension"). */
  label: string;
  /** The trigger's icon (`columns`, `plus`). */
  icon?: IconName;
  chosen: readonly string[];
  onChange: (chosen: string[]) => void;
}

export function FeaturePicker({ label, icon = 'columns', chosen, onChange }: FeaturePickerProps) {
  const catalogue = useFeatureCatalogue();
  const features = useMemo(() => catalogue.data ?? [], [catalogue.data]);
  const options = useMemo(() => featureOptions(features, chosen), [features, chosen]);
  const known = useMemo(() => byName(features), [features]);
  return (
    <Popover
      label={label}
      width="wide"
      trapFocus
      trigger={(props) => (
        <Button {...props} variant={icon === 'plus' ? 'dashed' : 'secondary'} size="sm" icon={icon}>
          {label}
        </Button>
      )}
    >
      <Stack gap={3}>
        <Field
          label="Add from the feature catalogue"
          hint="Type a name, a unit or a word of the description."
        >
          <Combobox
            options={options}
            value={null}
            onValueChange={(value) => {
              if (value) onChange([...chosen, value]);
            }}
            loading={catalogue.isPending}
            {...(catalogue.isError ? { error: 'The feature catalogue failed to load.' } : {})}
            emptyMessage="No feature matches"
            placeholder="iv30, market cap, earnings…"
            mono
          />
        </Field>
        <Stack gap={1}>
          <Text size="sm" tone="muted">
            {chosen.length === 0 ? 'Nothing chosen yet.' : `Chosen (${chosen.length})`}
          </Text>
          <Stack direction="row" gap={1} wrap>
            {chosen.map((name) => {
              const feature = known.get(name);
              const marks = feature ? featureMarks(feature) : [];
              return (
                <Chip
                  key={name}
                  label={[featureLabel(name), ...marks].join(' · ')}
                  onRemove={() => {
                    onChange(chosen.filter((c) => c !== name));
                  }}
                />
              );
            })}
          </Stack>
        </Stack>
      </Stack>
    </Popover>
  );
}
