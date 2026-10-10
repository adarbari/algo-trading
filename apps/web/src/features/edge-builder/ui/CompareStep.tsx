/**
 * Step 5, Compare against: the universe that sets the base rate (the selection presets the
 * screens use) and the decoy screens the edge must beat.
 */
import { Checkbox, Field, Select, Skeleton, Stack } from '@algotrade/ui';
import { useMemo } from 'react';

import { useScreeners } from '@/entities/screen';

import type { StepProps } from './step';

export function CompareStep({ draft, onChange }: StepProps) {
  const screeners = useScreeners();
  const universes = useMemo(
    () =>
      [
        ...new Set(
          [...(screeners.data ?? []).map((s) => s.selection ?? ''), draft.universe].filter(Boolean),
        ),
      ].sort(),
    [screeners.data, draft.universe],
  );
  const ids = useMemo(
    () =>
      [...new Set([...(screeners.data ?? []).map((s) => s.configId), ...draft.baselines])].sort(),
    [screeners.data, draft.baselines],
  );
  if (screeners.isPending) return <Skeleton lines={4} label="Loading screens…" />;
  return (
    <Stack gap={3}>
      <Field label="Universe" required>
        <Select
          options={universes.map((u) => ({ value: u, label: u }))}
          value={draft.universe}
          placeholder="Choose a universe"
          onValueChange={(universe) => {
            onChange({ universe });
          }}
        />
      </Field>
      <Stack gap={2} as="ul" aria-label="Decoys">
        {ids.map((id) => (
          <Stack as="li" key={id}>
            <Checkbox
              label={id}
              checked={draft.baselines.includes(id)}
              onCheckedChange={(on) => {
                onChange({
                  baselines: on
                    ? [...draft.baselines, id]
                    : draft.baselines.filter((b) => b !== id),
                });
              }}
            />
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
}
