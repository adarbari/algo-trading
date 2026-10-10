/**
 * Step 3, Picks: when the edge fires (every session, month end or on an event) and how many of
 * the screens' ranked stocks it takes (the top N, or all that qualify).
 */
import { Field, Grid, NumberInput, SegmentedControl, Select, Stack } from '@algotrade/ui';

import type { Schedule } from '../model/draft';
import { EVENTS, SCHEDULES, TAKES } from '../model/options';
import type { StepProps } from './step';

export function PicksStep({ draft, onChange }: StepProps) {
  return (
    <Grid columns={2} gap={3} collapse="md" align="start">
      <Stack gap={3}>
        <Field label="Fires">
          <SegmentedControl<Schedule>
            aria-label="Fires"
            options={SCHEDULES}
            value={draft.schedule}
            onValueChange={(schedule) => {
              onChange({ schedule });
            }}
          />
        </Field>
        {draft.schedule === 'on_event' && (
          <Field label="Event">
            <Select
              options={EVENTS}
              value={draft.event}
              onValueChange={(event) => {
                onChange({ event });
              }}
            />
          </Field>
        )}
      </Stack>
      <Stack gap={3}>
        <Field label="Take">
          <SegmentedControl
            aria-label="Take"
            options={TAKES}
            value={draft.take}
            onValueChange={(take) => {
              onChange({ take });
            }}
          />
        </Field>
        {draft.take === 'top' && (
          <Field label="N" required>
            <NumberInput
              value={draft.topK}
              min={1}
              step={1}
              precision={0}
              onValueChange={(topK) => {
                onChange({ topK });
              }}
            />
          </Field>
        )}
      </Stack>
    </Grid>
  );
}
