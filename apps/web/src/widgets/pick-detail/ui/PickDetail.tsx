/**
 * One pick of a screener's results, beside the table: the ticker with its decision and score, why
 * it is not simply qualified (a pick the regime gate paused says so, with the rule that did),
 * its criteria scorecard (value, rule, outcome), and the review actions (open in Explore, add to the compare set,
 * dismiss) with their keys. The chart and anything else about the ticker is composed beside it.
 */
import { ActionGroup, KeyHints, type KeyHint, Panel, Stack, Text } from '@algotrade/ui';

import type { CriterionInfo, TableRow } from '@/entities/feature';
import {
  CriteriaScorecard,
  DecisionBadge,
  decisionLabel,
  type ScorecardEntry,
} from '@/entities/screen';

export interface PickDetailProps {
  row: TableRow;
  /** The screener the pick is from (its rules are read from it). */
  screenerId: string;
  /** The screen's criteria in order (labels, fields); the gates have no row here. */
  criteria: readonly CriterionInfo[];
  /** The ticker is in the compare set. */
  compared: boolean;
  onOpen: (symbol: string) => void;
  onToggleCompare: () => void;
  onDismiss: () => void;
  /** Draw the action row (default true); off where the host pins the same actions elsewhere (a phone sheet's footer). */
  showActions?: boolean;
}

/** The keyboard shortcuts of the picks table (its `rowKeys`), as hints; hidden under a coarse pointer. */
const KEY_HINTS: readonly KeyHint[] = [
  { keys: ['j', 'k'], label: 'move' },
  { keys: ['c'], label: 'compare' },
  { keys: ['x'], label: 'dismiss' },
  { keys: ['Enter'], label: 'open in Explore' },
];

export function PickDetail({
  row,
  screenerId,
  criteria,
  compared,
  onOpen,
  onToggleCompare,
  onDismiss,
  showActions = true,
}: PickDetailProps) {
  const symbol = row.symbol;
  const entries = criteria.map((c): ScorecardEntry => ({
    id: c.id,
    field: c.field,
    outcome: row.criteria?.[c.id]?.outcome ?? 'MISSING',
    value: row.criteria?.[c.id]?.value,
    distance: row.criteria?.[c.id]?.distance ?? null,
  }));
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
          <>
            <Text size="sm" tone="secondary">
              The regime gate held this pick back, so it is not an idea for this session. The rule
              that paused it:
            </Text>
            {row.reasons ? <Text size="sm">{row.reasons}</Text> : null}
          </>
        ) : null}
        {row.flags && row.flags.length > 0 ? (
          <Text size="sm" tone="muted">{`Flags: ${row.flags.join(', ')}`}</Text>
        ) : null}
        <CriteriaScorecard screenerId={screenerId} entries={entries} />
        {showActions ? (
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
        ) : null}
        <KeyHints hints={KEY_HINTS} />
      </Stack>
    </Panel>
  );
}
