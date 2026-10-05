/**
 * One pick of a screener's results, beside the table: the ticker with its decision and score, why
 * it is not simply qualified, every criterion with the value it was judged on and whether it
 * passed, came near or missed, and the review actions (open in Explore, add to the compare set,
 * dismiss) with their keys. The chart and anything else about the ticker is composed beside it.
 */
import {
  Button,
  formatValue,
  Kbd,
  KeyValue,
  Mono,
  Panel,
  Stack,
  StatusBadge,
  Text,
  type KeyValueItem,
  type StatusTone,
} from '@algotrade/ui';
import { useMemo } from 'react';

import {
  byName,
  displayValue,
  featureFormat,
  featureLabel,
  useFeatureCatalogue,
} from '@/entities/feature';
import { DecisionBadge, type CriterionHeader, type ScreenTableRow } from '@/entities/screen';

export interface PickDetailProps {
  row: ScreenTableRow;
  /** The screen's criteria in order (labels, fields); the gates have no row here. */
  criteria: readonly CriterionHeader[];
  /** The ticker is in the compare set. */
  compared: boolean;
  onOpen: (symbol: string) => void;
  onToggleCompare: () => void;
  onDismiss: () => void;
}

const TONE: Readonly<Record<string, StatusTone>> = {
  PASS: 'positive',
  NEAR: 'warning',
  FAIL: 'negative',
  MISSING: 'negative',
};
const WORDS: Readonly<Record<string, string>> = {
  PASS: 'Passed',
  NEAR: 'Near miss',
  FAIL: 'Missed',
  MISSING: 'No value',
};

export function PickDetail({
  row,
  criteria,
  compared,
  onOpen,
  onToggleCompare,
  onDismiss,
}: PickDetailProps) {
  const catalogue = useFeatureCatalogue();
  const known = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const symbol = row.symbol ?? row.instrument_id;
  const items = criteria
    .filter((c) => !c.field.startsWith('instrument.'))
    .map((c): KeyValueItem => {
      const found = row.criteria[c.criterion_id];
      const feature = known.get(c.field);
      const outcome = found?.outcome ?? 'MISSING';
      const shown = found
        ? formatValue(displayValue(found.value), featureFormat(feature)).text
        : '—';
      return {
        id: c.criterion_id,
        label: feature ? featureLabel(feature.name) : c.criterion_id,
        value: (
          <Stack direction="row" gap={2} align="center" justify="end">
            <Mono size="sm">{shown}</Mono>
            <StatusBadge tone={TONE[outcome] ?? 'neutral'}>{WORDS[outcome] ?? outcome}</StatusBadge>
          </Stack>
        ),
      };
    });
  return (
    <Panel
      title={symbol}
      description={row.name ?? undefined}
      actions={<DecisionBadge decision={row.decision} />}
    >
      <Stack gap={3}>
        <Text size="sm" tone="secondary">
          {[
            row.score === null ? null : `Score ${String(Math.round(row.score))}`,
            row.change === 'new' ? 'new since the previous run' : null,
            row.change === 'dropped' ? `dropped (was ${row.previous_decision ?? 'n/a'})` : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </Text>
        {row.reasons ? <Text size="sm">{row.reasons}</Text> : null}
        {row.flags.length > 0 ? (
          <Text size="sm" tone="muted">{`Flags: ${row.flags.join(', ')}`}</Text>
        ) : null}
        <KeyValue label="Criteria" items={items} alignValues="end" />
        <Stack direction="row" gap={2} wrap>
          <Button
            size="sm"
            onClick={() => {
              onOpen(symbol);
            }}
          >
            Open in Explore
          </Button>
          <Button size="sm" onClick={onToggleCompare}>
            {compared ? 'Remove from compare' : 'Add to compare'}
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        </Stack>
        <Stack direction="row" gap={2} align="center" wrap>
          <Kbd keys={['j']} size="xs" />
          <Kbd keys={['k']} size="xs" />
          <Text size="xs" tone="muted">
            move
          </Text>
          <Kbd keys={['c']} size="xs" />
          <Text size="xs" tone="muted">
            compare
          </Text>
          <Kbd keys={['x']} size="xs" />
          <Text size="xs" tone="muted">
            dismiss
          </Text>
          <Kbd keys={['Enter']} size="xs" />
          <Text size="xs" tone="muted">
            open in Explore
          </Text>
        </Stack>
      </Stack>
    </Panel>
  );
}
