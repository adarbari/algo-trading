/**
 * Your train / test split: the site's frozen period per edge (read-only), the user's own split
 * (or none), a date input with Save and Clear. A saved split is the first session of the test
 * slice; results under it are labelled EXPLORATORY and come from `evaluate-edges`, which the
 * form says once after a save. The `exploratory` term carries the Guide button (`renderTermHelp`:
 * features never import each other). Checked here for form only; the API checks the range.
 */
import { Banner, Button, Field, Input, KeyValue, Mono, Panel, Stack, Text } from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import { useEvaluationSplit } from '@/entities/edge';
import { errorDetail } from '@/shared/api';

import { useSaveSplit } from '../api/hooks';
import { afterLatest, dateError } from '../model/date';

export interface EvaluationSplitFormProps {
  /** The Guide button for a glossary term (`exploratory`, `frozen_period`). */
  renderTermHelp?: (term: string) => ReactNode;
}

const SAVED =
  'Saved: results under your split are labelled EXPLORATORY and come from evaluate-edges.';
const CLEARED = 'Cleared. Each edge’s frozen period is the split again.';

export function EvaluationSplitForm({ renderTermHelp }: EvaluationSplitFormProps) {
  const split = useEvaluationSplit();
  const save = useSaveSplit();
  const [text, setText] = useState('');
  const [said, setSaid] = useState<string | null>(null);
  const read = split.data ?? null;
  if (read === null) return null;
  const typed = text.trim();
  const problem =
    typed === '' ? null : (dateError(typed) ?? afterLatest(typed, read.latestSession));
  const error = problem ?? (save.isError ? errorDetail(save.error) : undefined);
  const run = (value: string | null, message: string) => {
    save.mutate(value, {
      onSuccess: () => {
        setSaid(message);
        setText('');
      },
    });
  };
  const frozen = read.frozenPeriods.map((p) => ({
    id: p.edgeId,
    label: p.edgeId,
    value: <Mono>{p.frozenFrom}</Mono>,
  }));
  return (
    <Panel title="Train / test split" actions={renderTermHelp?.('exploratory')}>
      <Stack gap={3}>
        <Stack gap={1}>
          <Stack direction="row" gap={1} align="center">
            <Text size="sm" tone="secondary">
              Site frozen periods
            </Text>
            {renderTermHelp?.('frozen_period')}
          </Stack>
          {frozen.length > 0 ? (
            <KeyValue items={frozen} />
          ) : (
            <Text size="sm" tone="muted">
              No edge has a frozen period.
            </Text>
          )}
        </Stack>
        <Stack direction="row" gap={1} align="center">
          <Text size="sm" tone="secondary">
            Your split
          </Text>
          {read.splitFrom !== null ? (
            <Mono>{read.splitFrom}</Mono>
          ) : (
            <Text size="sm" tone="muted">
              None: each frozen period is the split
            </Text>
          )}
        </Stack>
        <Field
          label="Test slice starts"
          hint={`The first session of the test slice, up to ${read.latestSession}.`}
          error={error}
        >
          <Input
            value={text}
            onValueChange={setText}
            placeholder="2026-04-01"
            inputMode="numeric"
            autoComplete="off"
            mono
            width="auto"
          />
        </Field>
        <Stack direction="row" gap={2} wrap>
          <Button
            disabled={typed === '' || problem !== null || save.isPending}
            onClick={() => {
              run(typed, SAVED);
            }}
          >
            Save
          </Button>
          <Button
            variant="ghost"
            disabled={read.splitFrom === null || save.isPending}
            onClick={() => {
              run(null, CLEARED);
            }}
          >
            Clear
          </Button>
        </Stack>
        {said !== null && !save.isError && <Banner>{said}</Banner>}
      </Stack>
    </Panel>
  );
}
