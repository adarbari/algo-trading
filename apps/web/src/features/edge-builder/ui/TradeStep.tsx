/**
 * Step 4, Trade: when each pick is entered, the holding periods (each reported on its own), the
 * costs of a round trip and what counts as a win. A win test the builder has no control for (an
 * option edge's) is kept as the edge has it.
 */
import { Banner, Chip, Field, Grid, NumberInput, SegmentedControl, Stack } from '@algotrade/ui';

import { useMemo } from 'react';

import { HORIZON_CHOICES, WINS } from '../model/options';
import type { StepProps } from './step';

export function TradeStep({ draft, onChange }: StepProps) {
  const choices = useMemo(
    () => [...new Set([...HORIZON_CHOICES, ...draft.horizons])].sort((a, b) => a - b),
    [draft.horizons],
  );
  const toggle = (days: number, on: boolean) => {
    onChange({
      horizons: on
        ? [...draft.horizons, days].sort((a, b) => a - b)
        : draft.horizons.filter((h) => h !== days),
    });
  };
  return (
    <Grid columns={2} gap={3} collapse="md" align="start">
      <Field label="Enter, sessions after the trigger" required>
        <NumberInput
          value={draft.startOffset}
          min={1}
          step={1}
          precision={0}
          onValueChange={(startOffset) => {
            onChange({ startOffset });
          }}
        />
      </Field>
      <Field label="Costs per round trip">
        <NumberInput
          value={draft.costBps}
          min={0}
          step={1}
          suffix="bps"
          onValueChange={(costBps) => {
            onChange({ costBps });
          }}
        />
      </Field>
      <Stack gap={1}>
        <Field label="Holding periods, trading days" required>
          <Stack direction="row" gap={1} wrap aria-label="Holding periods">
            {choices.map((days) => (
              <Chip
                key={days}
                label={`${String(days)} days`}
                selected={draft.horizons.includes(days)}
                onSelectedChange={(on) => {
                  toggle(days, on);
                }}
              />
            ))}
          </Stack>
        </Field>
      </Stack>
      <Stack gap={2}>
        {draft.win === 'other' ? (
          <Banner tone="info" title="Win test kept">
            This edge's win test is set in its document and stays as it is.
          </Banner>
        ) : (
          <Field label="A win is">
            <SegmentedControl
              aria-label="A win is"
              options={WINS}
              value={draft.win}
              onValueChange={(win) => {
                onChange({ win });
              }}
            />
          </Field>
        )}
      </Stack>
    </Grid>
  );
}
