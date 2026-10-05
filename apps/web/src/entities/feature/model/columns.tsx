/**
 * The column factories (ADR 0038, read model WEB 4): every table column comes from one of
 * these, so a ticker, a decision or a catalogue feature reads the same in every table. A
 * table is a `ColumnPlan`, an ordered list of factory calls; no widget writes a column
 * literal. Each column's `id` is stable and is also the server's sort key for it: `symbol`,
 * `rank`, `decision`, `score`, `flags`, `change`, `criterion:<id>` and the catalogue name of a
 * feature column. A feature column reads its format from the server (`FeatureInfo.format`),
 * never from the feature's name, and shows UNKNOWN with the reason where the session has no
 * value.
 */
import { Mono, Stack, Text, isNumericFormat, type DataTableColumn } from '@algotrade/ui';

import { DecisionBadge, OUTCOME_FILL, decisionLabel } from '@/entities/screen';

import { featureLabel, featureMarks, unitLabel } from './catalogue';
import type { ColumnInfo, TableRow } from './table';
import { codeReason, shownValue, valueFormat } from './value';

/** A table's columns, in order: each one a factory call. */
export type ColumnPlan = readonly DataTableColumn<TableRow>[];

/** The ticker column's id (and the server's sort key for it). */
export const TICKER_COLUMN = 'symbol';

/** The ticker over the company or fund name. */
export function tickerColumn(): DataTableColumn<TableRow> {
  return {
    id: TICKER_COLUMN,
    header: 'Ticker',
    description: 'The ticker and the company or fund name',
    value: (row) => row.symbol,
    hideable: false,
    width: 'md',
    grow: true,
    cell: ({ row }) => (
      <Stack gap={0}>
        <Mono weight="medium">{row.symbol}</Mono>
        <Text size="xs" tone="muted" truncate title={row.name}>
          {row.name}
        </Text>
      </Stack>
    ),
  };
}

function describe(info: ColumnInfo): string {
  const unit = unitLabel(info.unit);
  const marks = featureMarks(info);
  const marked = marks.length > 0 ? ` (${marks.join(', ')})` : '';
  return `${info.description}${unit ? ` Unit: ${unit}.` : ''}${marked} [${info.name}]`;
}

/**
 * One catalogue feature: headed by its short label (personal-licence features marked `(P)`),
 * formatted by the server's `info.format`; a cell the session has no value for reads
 * "Unknown" with the reason.
 */
export function featureColumn(info: ColumnInfo): DataTableColumn<TableRow> {
  const format = valueFormat(info);
  const numeric = isNumericFormat(format);
  const label = featureLabel(info.name);
  return {
    id: info.name,
    header: info.licence === 'personal' ? `${label} (P)` : label,
    description: describe(info),
    value: (row) => shownValue(row.cells[info.name]?.value ?? null),
    format,
    hideable: false,
    cell: ({ row, formatted }) => {
      const cell = row.cells[info.name];
      if (!cell || cell.value === null || cell.value === undefined) {
        return (
          <Text tone="muted" title={codeReason(cell?.unknown ?? null, info.nullMeaning)}>
            Unknown
          </Text>
        );
      }
      return (
        <Text numeric={numeric} tone={formatted.tone}>
          {formatted.text}
        </Text>
      );
    },
  };
}

/** The rank in a screen's results (1 = best). */
export function rankColumn(): DataTableColumn<TableRow> {
  return {
    id: 'rank',
    header: '#',
    description: 'Rank by score, then the tie-break column',
    value: (row) => row.rank,
    format: { kind: 'number' },
    width: 'xs',
    hideable: false,
  };
}

/** The screen's decision as a badge. */
export function decisionColumn(): DataTableColumn<TableRow> {
  return {
    id: 'decision',
    header: 'Decision',
    description: "The screen's decision for the ticker",
    value: (row) => row.decision,
    width: 'lg',
    cell: ({ row }) => (row.decision ? <DecisionBadge decision={row.decision} /> : null),
  };
}

/** The screen's score (for sorting: 100 minus the penalties of each miss). */
export function scoreColumn(): DataTableColumn<TableRow> {
  return {
    id: 'score',
    header: 'Score',
    description: 'For sorting only: 100 minus the penalties of each miss',
    value: (row) => row.score,
    format: { kind: 'number', digits: 0 },
    width: 'xs',
  };
}

/** The flags a screen raised, in words. */
export function flagsColumn(): DataTableColumn<TableRow> {
  return {
    id: 'flags',
    header: 'Flags',
    value: (row) => (row.flags ?? []).map(decisionLabel).join(', ') || null,
    tone: 'secondary',
    sortable: false,
    width: 'lg',
  };
}

/** A criterion of a screen: what it judged and how. */
export interface CriterionInfo {
  id: string;
  /** The catalogue field it reads. */
  field: string;
  mode: string;
}

/**
 * One criterion: its value, formatted as its feature (`info`, when the catalogue has it), the
 * cell tinted by the outcome (a near miss or a miss); the value still says what it is.
 */
export function criterionColumn(
  criterion: CriterionInfo,
  info?: ColumnInfo,
): DataTableColumn<TableRow> {
  const of = (row: TableRow) => row.criteria?.[criterion.id];
  return {
    id: `criterion:${criterion.id}`,
    header: info ? featureLabel(info.name) : decisionLabel(criterion.id),
    description: `${info?.description ?? criterion.field} (criterion ${criterion.id}, ${criterion.mode}). A tint marks a near miss or a miss.`,
    value: (row) => shownValue(of(row)?.value ?? null),
    format: info ? valueFormat(info) : { kind: 'number', digits: 2 },
    fill: (row) => OUTCOME_FILL[of(row)?.outcome ?? ''],
  };
}

/** New or dropped since the previous run (the server decides). */
export function changeColumn(): DataTableColumn<TableRow> {
  return {
    id: 'change',
    header: 'Change',
    description: 'New or dropped since the previous run',
    value: (row) => (row.change ? decisionLabel(row.change) : null),
    tone: 'secondary',
    width: 'sm',
  };
}
