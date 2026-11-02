/**
 * The rows inside a part card of the review: the criteria the part owns (id and field, with the
 * field's Guide help), what the draft left out of it, the picker of another reading for an
 * ambiguous term.
 */
import { Mono, SegmentedControl, Stack, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';

import type { ScreenDraft, Unresolved } from '@/features/screener-describe';

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
