/**
 * The rows inside a part card of the review: the criteria the part owns (id and field, with the
 * field's Guide help), what the draft left out of it, the picker of another reading for an
 * ambiguous term, and the Suggested group (protective checks, soft or score, each added or
 * skipped by the trader, never applied on their own).
 */
import { Button, Mono, SegmentedControl, Stack, StatusBadge, Surface, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { termHelp } from '@/features/guide-help';
import {
  PART_TEXT,
  type DraftSuggestion,
  type ScreenDraft,
  type Unresolved,
} from '@/features/screener-describe';

type Dropped = ScreenDraft['dropped'][number];

export function CriteriaRows({
  rows,
  dropped,
  renderFieldHelp,
}: {
  rows: readonly { id: string; field: string }[];
  dropped: readonly Dropped[];
  renderFieldHelp?: ((field: string) => ReactNode) | undefined;
}) {
  return (
    <Stack gap={1}>
      {rows.map(({ id, field }) => (
        <Stack key={id} direction="row" gap={1} align="center" wrap>
          <Text size="sm" tone="muted">{`${id}:`}</Text>
          <Mono size="sm">{field}</Mono>
          {renderFieldHelp?.(field)}
        </Stack>
      ))}
      {dropped.map((d) => (
        <Stack key={d.id} direction="row" gap={1} align="center" wrap>
          <Text size="sm">{`Left out ${d.id} (`}</Text>
          <Mono size="sm">{d.field}</Mono>
          {renderFieldHelp?.(d.field)}
          <Text size="sm">{`): ${d.reason}`}</Text>
        </Stack>
      ))}
    </Stack>
  );
}

export function Readings({
  term,
  selected,
  swappable,
  onPick,
}: {
  term: Unresolved;
  selected: number;
  swappable: boolean;
  onPick: (to: number) => void;
}) {
  return (
    <Stack gap={1}>
      <Mono size="sm">{term.term}</Mono>
      <SegmentedControl
        aria-label={`Reading of ${term.term}`}
        options={term.alternatives.map((alternative, i) => ({
          value: String(i),
          label: alternative.text,
        }))}
        value={String(selected)}
        disabled={!swappable}
        onValueChange={(value) => {
          onPick(Number(value));
        }}
      />
    </Stack>
  );
}

export type SuggestionState = 'added' | 'skipped';

/** The Suggested group: each protective check with its why, Add / Skip while undecided. */
export function Suggested({
  suggestions,
  states,
  onAdd,
  onSkip,
  renderFieldHelp,
}: {
  suggestions: readonly DraftSuggestion[];
  states: Readonly<Record<string, SuggestionState>>;
  onAdd: (suggestion: DraftSuggestion) => void;
  onSkip: (id: string) => void;
  renderFieldHelp?: ((field: string) => ReactNode) | undefined;
}) {
  if (suggestions.length === 0) return null;
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Text size="sm" weight="semibold">
          {PART_TEXT.suggested}
        </Text>
        {termHelp(PART_TEXT.suggestedHelp.id)}
      </Stack>
      {suggestions.map((suggestion) => {
        const state = states[suggestion.id];
        const field =
          typeof suggestion.criterion['field'] === 'string' ? suggestion.criterion['field'] : '';
        return (
          <Surface key={suggestion.id} tone="row" padding={2} radius="md">
            <Stack gap={1}>
              <Stack direction="row" gap={1} align="center" wrap>
                <Mono size="sm">{field}</Mono>
                {renderFieldHelp?.(field)}
                {state && (
                  <StatusBadge tone={state === 'added' ? 'positive' : 'neutral'}>
                    {state === 'added' ? PART_TEXT.added : PART_TEXT.skipped}
                  </StatusBadge>
                )}
              </Stack>
              <Text size="sm" tone="muted">
                {suggestion.why}
              </Text>
              {!state && (
                <Stack direction="row" gap={2}>
                  <Button
                    variant="secondary"
                    size="sm"
                    aria-label={`${PART_TEXT.add} ${field}`}
                    onClick={() => {
                      onAdd(suggestion);
                    }}
                  >
                    {PART_TEXT.add}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`${PART_TEXT.skip} ${field}`}
                    onClick={() => {
                      onSkip(suggestion.id);
                    }}
                  >
                    {PART_TEXT.skip}
                  </Button>
                </Stack>
              )}
            </Stack>
          </Surface>
        );
      })}
    </Stack>
  );
}
