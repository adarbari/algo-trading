/**
 * The criteria of one screener's judgement of one ticker, the same list wherever it is shown
 * (the pick under review, a screener's hit in Explore): per criterion its field, the value in
 * the field's format, the rule from the screen (read from the screen's own criteria), how far a
 * near miss or a miss was from passing, and the outcome. The gates (who is screened) have no
 * line. Entries come as the run served them, in the screen's order.
 */
import { KeyValue, Mono, Stack, StatusBadge, Text, type KeyValueItem } from '@algotrade/ui';
import { useMemo } from 'react';

import { byName, useFeatureCatalogue } from '@/entities/feature';

import { useScreener } from '../api/hooks';
import { outcomeLabel, outcomeTone } from '../model/decisions';
import { isShownCriterion } from '../model/results';
import { scorecardRows, type ScorecardEntry } from '../model/scorecard';
import { criteriaOf, type Criterion } from '../model/spec';

export interface CriteriaScorecardProps {
  /** The screener the criteria belong to (its rules are read from it). */
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
  const detail = useScreener(screenerId);
  const features = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const rules = useMemo(
    () =>
      new Map<string, Criterion>(
        criteriaOf(detail.data?.resolved, { id: screenerId }).map((c) => [c.id, c]),
      ),
    [detail.data, screenerId],
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
