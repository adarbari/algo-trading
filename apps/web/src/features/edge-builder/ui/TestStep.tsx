/**
 * Step 6, Test and run: the edge's own out-of-sample start (before it is in-sample, from it is
 * kept aside; results stay hidden while the user tweaks), a summary of the draft, how many
 * variants were tried, and the two saves.
 */
import { Button, Field, Input, KeyValue, NoticeLine, Stack } from '@algotrade/ui';

import { isIsoDate } from '../model/date';
import { useHelp } from '../model/help';
import { summaryOf } from '../model/summary';
import type { StepProps } from './step';

export interface TestStepProps extends StepProps {
  /** Variants tried on this edge so far (the most any of its runs counted). */
  trials: number;
  /** Nothing blocks saving. */
  ready: boolean;
  saving: boolean;
  onSave: (run: boolean) => void;
}

export function TestStep({ draft, onChange, trials, ready, saving, onSave }: TestStepProps) {
  const help = useHelp();
  const bad = draft.frozenFrom !== '' && !isIsoDate(draft.frozenFrom);
  return (
    <Stack gap={3}>
      <Field
        label="Out-of-sample from"
        hint="yyyy-mm-dd; empty: none"
        error={bad ? 'Use a real day written yyyy-mm-dd.' : undefined}
      >
        <Input
          value={draft.frozenFrom}
          onValueChange={(frozenFrom) => {
            onChange({ frozenFrom: frozenFrom.trim() });
          }}
          placeholder="2026-04-01"
          mono
          autoComplete="off"
          width="auto"
        />
      </Field>
      <KeyValue label="Summary" items={summaryOf(draft)} />
      {trials > 0 && (
        <Stack direction="row" gap={2} align="center">
          <NoticeLine
            tone="warning"
            label={`${String(trials)} variants tried`}
            summary="on this edge so far"
          />
          {help('edge_variants_tried')}
        </Stack>
      )}
      <Stack direction="row" gap={2} wrap>
        <Button
          variant="secondary"
          disabled={!ready || bad}
          loading={saving}
          onClick={() => {
            onSave(false);
          }}
        >
          Save
        </Button>
        <Button
          variant="primary"
          disabled={!ready || bad}
          loading={saving}
          onClick={() => {
            onSave(true);
          }}
        >
          Save and run backtest
        </Button>
      </Stack>
    </Stack>
  );
}
