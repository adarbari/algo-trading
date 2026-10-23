/**
 * The two columns that tie a pick to its evidence (ADR 0053): "Why it matched", the rules the
 * pick passed with the value each judged, in the field's own format, and "Counts toward", what
 * each edge that lists the screener does with it. Both read what the run served (the rule values
 * and the server's `countsToward`); nothing is counted or recomputed here. Also the words and
 * Guide entries of each reason a pick is or is not counted, shared with the pick's detail.
 */
import { formatValue, Stack, StatusBadge, Text, type StatusTone } from '@algotrade/ui';

import { featureLabel } from './catalogue';
import type { CriterionInfo, PlanColumn } from './columns';
import type { ColumnInfo, PickEdge, TableRow } from './table';
import { shownValue, valueFormat } from './value';

/** The Guide term behind each reason a pick is or is not counted (`PickEdge.code`). */
export const PICK_EDGE_TERM: Readonly<Record<string, string>> = {
  counts: 'edge_pick_counts',
  paused: 'edge_pick_paused',
  not_counted: 'edge_pick_not_counted',
  not_a_decision_day: 'edge_pick_not_a_decision_day',
  withheld: 'edge_pick_withheld',
  unjudged: 'edge_pick_unjudged',
  not_stored: 'edge_pick_not_stored',
};

const WORDS: Readonly<Record<string, string>> = {
  counts: 'Counts',
  paused: 'Held back by the regime gate',
  not_counted: 'Not counted',
  not_a_decision_day: 'Not a decision day',
  withheld: 'Not judged',
  unjudged: 'Not judged: other side',
  not_stored: 'Picks not stored',
};

/** The short words of a pick's verdict under one edge. */
export function pickEdgeWords(edge: PickEdge): string {
  return WORDS[edge.code] ?? 'Not judged';
}

export function pickEdgeTone(edge: PickEdge): StatusTone {
  return edge.counts ? 'positive' : 'neutral';
}

/** Cap of edges named in a table cell; the rest are a count (the detail lists them all). */
const CELL_EDGES = 2;

/**
 * What a pick counts toward, one line per edge: a badge (counted or not, with the reason) and
 * the edge's name. No line when no edge lists the screener.
 */
export function countsTowardColumn(): PlanColumn {
  const edges = (row: TableRow) => row.countsToward ?? [];
  return {
    id: 'counts_toward',
    help: { kind: 'term', id: 'counts_toward' },
    header: 'Counts toward',
    description: 'The edges that list this screener, and whether each counts this pick',
    value: (row) => edges(row).filter((e) => e.counts).length,
    width: 'xl',
    sortable: false,
    cell: ({ row }) => {
      const found = edges(row);
      if (found.length === 0) return null;
      return (
        <Stack gap={1}>
          {found.slice(0, CELL_EDGES).map((e) => (
            <Stack key={e.edgeId} direction="row" gap={1} align="center" wrap>
              <StatusBadge tone={pickEdgeTone(e)}>{pickEdgeWords(e)}</StatusBadge>
              <Text size="sm" tone="secondary">
                {e.edgeName}
              </Text>
            </Stack>
          ))}
          {found.length > CELL_EDGES ? (
            <Text size="xs" tone="muted">{`+${String(found.length - CELL_EDGES)} more edges`}</Text>
          ) : null}
        </Stack>
      );
    },
  };
}

/** The rules the pick passed, as "label value" in the field's format, joined with a middle dot. */
export function matchedText(
  row: TableRow,
  criteria: readonly CriterionInfo[],
  features: ReadonlyMap<string, ColumnInfo>,
): string {
  const parts: string[] = [];
  for (const c of criteria) {
    const judged = row.criteria?.[c.id];
    const info = features.get(c.field);
    if (c.field.startsWith('instrument.') || judged?.outcome !== 'PASS') continue;
    if (judged.value === null || judged.value === undefined) continue;
    const text = info
      ? formatValue(shownValue(judged.value), valueFormat(info)).text
      : `${judged.value as string | number}`;
    parts.push(`${info ? featureLabel(info.name) : c.id} ${text}`);
  }
  return parts.join(' · ');
}

/**
 * "Why it matched": each rule the pick passed with its value. A pick that failed or only nearly
 * met a rule shows the rules it did pass here and what it missed in the Why column.
 */
export function matchedColumn(
  criteria: readonly CriterionInfo[],
  features: ReadonlyMap<string, ColumnInfo>,
): PlanColumn {
  return {
    id: 'matched',
    help: { kind: 'term', id: 'why_it_matched' },
    header: 'Why it matched',
    description: 'The rules this pick passed, each with the value it was judged on',
    value: (row) => matchedText(row, criteria, features) || null,
    grow: true,
    width: 'xl',
    sortable: false,
    tone: 'secondary',
  };
}
