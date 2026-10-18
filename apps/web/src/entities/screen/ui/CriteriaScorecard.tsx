/**
 * The criteria of one screener's judgement of one ticker, the same list wherever it is shown
 * (the pick under review, a screener's hit in Explore): per criterion its field, the value in
 * the field's format, the rule from the screen (the typed criteria of its `Screener`), how far a
 * near miss or a miss was from passing, and the outcome. The gates (who is screened) have no
 * line. Entries come as the run served them, in the screen's order. A group (ADR 0071) is one
 * expandable row with its outcome and the member that decided it; its members open under it.
 */
import { KeyValue, Mono, Stack, StatusBadge, Text, type KeyValueItem } from '@algotrade/ui';
import { useMemo, type ReactNode } from 'react';

import { byName, useFeatureCatalogue } from '@/entities/feature';

import { useScreenerRuns } from '../api/runs';
import { outcomeLabel, outcomeTone } from '../model/decisions';
import { isShownCriterion } from '../model/results';
import {
  scorecardRows,
  type ScorecardEntry,
  type ScorecardGroup,
  type ScorecardRow,
} from '../model/scorecard';
import { toCriteria } from '../model/criteria-lines';
import type { Criterion } from '../model/spec';

/** A group to draw: its definition, the labels of its members and its rendered members. */
export interface ScorecardGate {
  group: ScorecardGroup;
  /** Member labels in order (a nested group is named by its id). */
  names: string[];
  /** The label of the member that decided it, if the run says. */
  decidedBy: string | null;
  members: ReactNode[];
}

export interface CriteriaScorecardProps {
  /** The screener the criteria belong to (its rules are the typed criteria of its `Screener`). */
  screenerId: string;
  entries: readonly ScorecardEntry[];
  /** The screen's groups as this pick's run judged them (ADR 0071); none: a flat list. */
  groups?: readonly ScorecardGroup[];
  /**
   * Draws one gate that is a group: its members already rendered. The host passes it (the Guide
   * help for the kind lives in features, which an entity cannot import); without it the groups
   * are not drawn and the criteria list flat.
   */
  renderGroup?: (gate: ScorecardGate) => ReactNode;
  /** Accessible name of the list (default: Criteria). */
  label?: string;
}

export function CriteriaScorecard({
  screenerId,
  entries,
  groups = [],
  renderGroup,
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
  const line = (row: ScorecardRow): KeyValueItem => ({
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
  });
  const byId = new Map(rows.map((row) => [row.id, row]));
  const segments = renderGroup ? scorecardSegments(rows, groups) : [];
  if (!renderGroup || segments.every((segment) => segment.type === 'rows')) {
    return (
      <KeyValue
        label={label}
        items={rows.map(line)}
        alignValues="end"
        emptyMessage="No criteria."
      />
    );
  }
  const byGroup = new Map(groups.map((g) => [g.id, g]));
  const render = renderGroup;
  const group = (g: ScorecardGroup): ReactNode => {
    const members: ReactNode[] = [];
    for (const id of g.members) {
      const nested = byGroup.get(id);
      const row = byId.get(id);
      if (nested) members.push(group(nested));
      else if (row) {
        members.push(<KeyValue key={id} label={row.label} items={[line(row)]} alignValues="end" />);
      }
    }
    return render({
      group: g,
      names: g.members.map((id) => byId.get(id)?.label ?? byGroup.get(id)?.id ?? id),
      decidedBy: g.decidedBy ? (byId.get(g.decidedBy)?.label ?? g.decidedBy) : null,
      members,
    });
  };
  return (
    <Stack gap={2} as="div" aria-label={label}>
      {segments.map((segment, index) =>
        segment.type === 'rows' ? (
          <KeyValue
            key={`rows-${String(index)}`}
            label={label}
            items={segment.rows.map(line)}
            alignValues="end"
          />
        ) : (
          group(segment.group)
        ),
      )}
    </Stack>
  );
}

type Segment = { type: 'rows'; rows: ScorecardRow[] } | { type: 'group'; group: ScorecardGroup };

/** The rows in order with each gate (a top-level group) once, at its first shown member. */
function scorecardSegments(
  rows: readonly ScorecardRow[],
  groups: readonly ScorecardGroup[],
): Segment[] {
  const parent = new Map(groups.flatMap((g) => g.members.map((m) => [m, g.id] as const)));
  const byGroup = new Map(groups.map((g) => [g.id, g]));
  const segments: Segment[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    let top: string | undefined;
    for (let id = parent.get(row.id); id !== undefined; id = parent.get(id)) top = id;
    const gate = top === undefined ? undefined : byGroup.get(top);
    if (!gate) {
      const last = segments.at(-1);
      if (last?.type === 'rows') last.rows.push(row);
      else segments.push({ type: 'rows', rows: [row] });
    } else if (!seen.has(gate.id)) {
      seen.add(gate.id);
      segments.push({ type: 'group', group: gate });
    }
  }
  return segments;
}
