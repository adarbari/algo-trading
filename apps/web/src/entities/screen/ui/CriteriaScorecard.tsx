/**
 * The criteria of one screener's judgement of one ticker, the same list wherever it is shown
 * (the pick under review, a screener's hit in Explore): per criterion its field, the value in
 * the field's format, the rule from the screen (the typed criteria of its `Screener`), how far a
 * near miss or a miss was from passing, and the outcome. The gates (who is screened) have no
 * line. Entries come as the run served them, in the screen's order.
 */
import { KeyValue, Mono, Stack, StatusBadge, Text, type KeyValueItem } from '@algotrade/ui';
import { useMemo } from 'react';

import { byName, useFeatureCatalogue } from '@/entities/feature';

import { useScreenerRuns } from '../api/runs';
import { outcomeLabel, outcomeTone } from '../model/decisions';
import { isShownCriterion } from '../model/results';
import { scorecardRows, type ScorecardEntry } from '../model/scorecard';
import { toCriteria } from '../model/criteria-lines';
import type { Criterion } from '../model/spec';

export interface CriteriaScorecardProps {
  /** The screener the criteria belong to (its rules are the typed criteria of its `Screener`). */
  screenerId: string;
  entries: readonly ScorecardEntry[];
  /** Accessible name of the list (default: Criteria). */
  label?: string;
}

export function CriteriaScorecard({
  screenerId,
  entries,
  label = 'Criteria',
}: CriteriaScorecardProps) {
  const catalogue = useFeatureCatalogue();
  const runs = useScreenerRuns();
  const features = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const rules = useMemo(
    () =>
      new Map<string, Criterion>(
        toCriteria(runs.data?.byId.get(screenerId)?.criteria).map((c) => [c.id, c]),
      ),
    [runs.data, screenerId],
  );
  const rows = scorecardRows(entries.filter(isShownCriterion), features, rules);
  const items = rows.map((row): KeyValueItem => ({
    id: row.id,
    label: row.label,
    hint: row.rule || undefined,
    value: (
      <Stack direction="row" gap={2} align="center" justify="end" wrap>
        <Mono size="sm">{row.value}</Mono>
        {row.distance === null ? null : (
          <Text size="sm" tone="muted">{`short by ${row.distance}`}</Text>
        )}
        <StatusBadge tone={outcomeTone(row.outcome)}>{outcomeLabel(row.outcome)}</StatusBadge>
      </Stack>
    ),
  }));
  return <KeyValue label={label} items={items} alignValues="end" emptyMessage="No criteria." />;
}
