/**
 * One pick of a screener's results, beside the table: the ticker with its decision and score, why
 * it is not simply qualified (a pick the regime gate paused says so, with the rule that did), every criterion with the value it was judged on and whether it
 * passed, came near or missed, and the review actions (open in Explore, add to the compare set,
 * dismiss) with their keys. The chart and anything else about the ticker is composed beside it.
 */
import {
  ActionGroup,
  formatValue,
  KeyHints,
  type KeyHint,
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
  type CriterionInfo,
  type TableRow,
} from '@/entities/feature';
import { DecisionBadge, decisionLabel, isShownCriterion } from '@/entities/screen';

export interface PickDetailProps {
  row: TableRow;
  /** The screen's criteria in order (labels, fields); the gates have no row here. */
  criteria: readonly CriterionInfo[];
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

/** The keyboard shortcuts of the picks table (its `rowKeys`), as hints; hidden under a coarse pointer. */
const KEY_HINTS: readonly KeyHint[] = [
  { keys: ['j', 'k'], label: 'move' },
  { keys: ['c'], label: 'compare' },
  { keys: ['x'], label: 'dismiss' },
  { keys: ['Enter'], label: 'open in Explore' },
];

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
  const symbol = row.symbol;
  const items = criteria.filter(isShownCriterion).map((c): KeyValueItem => {
    const found = row.criteria?.[c.id];
    const feature = known.get(c.field);
    const outcome = found?.outcome ?? 'MISSING';
    const shown = found ? formatValue(displayValue(found.value), featureFormat(feature)).text : '—';
    return {
      id: c.id,
      label: feature ? featureLabel(feature.name) : c.id,
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
      description={row.name || undefined}
      actions={row.decision ? <DecisionBadge decision={row.decision} /> : null}
    >
      <Stack gap={3}>
        <Text size="sm" tone="secondary">
          {[
            row.score === null || row.score === undefined
              ? null
              : `Score ${String(Math.round(row.score))}`,
            row.change === 'new' ? 'new since the previous run' : null,
            row.change === 'dropped'
              ? `dropped (was ${row.previousDecision ? decisionLabel(row.previousDecision).toLowerCase() : 'n/a'})`
              : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </Text>
        {row.decision === 'PAUSED' ? (
          <Text size="sm" tone="secondary">
            The regime gate held this pick back, so it is not an idea for this session. The rule
            that paused it:
          </Text>
        ) : null}
        {row.reasons ? <Text size="sm">{row.reasons}</Text> : null}
        {row.flags && row.flags.length > 0 ? (
          <Text size="sm" tone="muted">{`Flags: ${row.flags.join(', ')}`}</Text>
        ) : null}
        <KeyValue label="Criteria" items={items} alignValues="end" />
        <ActionGroup
          label="Pick actions"
          actions={[
            {
              id: 'open',
              label: 'Open in Explore',
              icon: 'external',
              onClick: () => {
                onOpen(symbol);
              },
            },
            {
              id: 'compare',
              label: compared ? 'Remove from compare' : 'Add to compare',
              icon: compared ? 'minus' : 'plus',
              onClick: onToggleCompare,
            },
            {
              id: 'dismiss',
              label: 'Dismiss',
              icon: 'close',
              variant: 'ghost',
              onClick: onDismiss,
            },
          ]}
        />
        <KeyHints hints={KEY_HINTS} />
      </Stack>
    </Panel>
  );
}
