/**
 * The column factories (ADR 0038, read model WEB 4): every table column comes from one of
 * these, so a ticker, a decision or a catalogue feature reads the same in every table. A
 * table is a `ColumnPlan`, an ordered list of factory calls; no widget writes a column
 * literal. Each column's `id` is stable and is also the server's sort key for it: `symbol`,
 * `rank`, `decision`, `score`, `flags`, `change`, `reasons`, `criterion:<id>`, `column:<name>`
 * (a screen's display column) and the catalogue name of a feature column. A feature column reads its format from the server (`FeatureInfo.format`),
 * never from the feature's name, and shows UNKNOWN with the reason where the session has no
 * value.
 */
import {
  Mono,
  Stack,
  StatusBadge,
  Text,
  isNumericFormat,
  type DataTableColumn,
} from '@algotrade/ui';

import { DecisionBadge, OUTCOME_FILL, ScoreBreakdown, decisionLabel } from '@/entities/screen';

import { featureLabel, featureMarks, unitLabel } from './catalogue';
import type { ColumnInfo, TableRow } from './table';
import { codeReason, shownValue, unknownLabel, valueFormat } from './value';

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
 * "Unknown" (or "n/a" / "Illiquid", ADR 0042) with the reason.
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
            {unknownLabel(cell?.unknown ?? null)}
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

const NO_TICKERS: ReadonlySet<string> = new Set();

/**
 * The screen's decision as a badge; a ticker in `leaving` (the unsaved criteria would drop it
 * from the picks: the server's preview changes) is marked "Would leave".
 */
export function decisionColumn(
  leaving: ReadonlySet<string> = NO_TICKERS,
): DataTableColumn<TableRow> {
  return {
    id: 'decision',
    header: 'Decision',
    description: "The screen's decision for the ticker",
    value: (row) => row.decision,
    width: 'lg',
    cell: ({ row }) =>
      row.decision ? (
        <Stack gap={0}>
          <DecisionBadge decision={row.decision} />
          {leaving.has(row.symbol) ? <StatusBadge tone="warning">Would leave</StatusBadge> : null}
        </Stack>
      ) : null,
  };
}

/**
 * The screen's score (for sorting: 100 minus the penalties of each miss); a preview row's
 * opens how it was worked out (`labelOf` names a criterion: its catalogue label).
 */
export function scoreColumn(
  labelOf?: (criterionId: string, field: string) => string,
): DataTableColumn<TableRow> {
  return {
    id: 'score',
    header: 'Score',
    description: 'For sorting only: 100 minus the penalties of each miss',
    value: (row) => row.score,
    format: { kind: 'number', digits: 0 },
    width: 'xs',
    cell: ({ row, formatted }) =>
      row.scoring ? (
        <ScoreBreakdown row={row.scoring} {...(labelOf ? { labelOf } : {})} />
      ) : (
        <Text numeric>{formatted.text}</Text>
      ),
  };
}

/** Why the decision is not QUALIFIED (the misses), in words. */
export function reasonsColumn(): DataTableColumn<TableRow> {
  return {
    id: 'reasons',
    header: 'Why',
    description: 'The misses behind a decision other than QUALIFIED',
    value: (row) => row.reasons || null,
    grow: true,
    tone: 'secondary',
    sortable: false,
  };
}

/** One of a screen's display columns (`[columns]`): the value the run stored for it. */
export interface ScreenColumnInfo {
  name: string;
  /** The catalogue field it shows. */
  field: string;
}

/**
 * A screen's display column, headed and formatted as its feature (`info`, when the catalogue
 * has it), else by its own name as a number.
 */
export function screenColumn(
  column: ScreenColumnInfo,
  info?: ColumnInfo,
): DataTableColumn<TableRow> {
  return {
    id: `column:${column.name}`,
    header: info ? featureLabel(info.name) : decisionLabel(column.name),
    description: `${info?.description ?? column.field} (the screen's column ${column.name})`,
    value: (row) => shownValue(row.columns?.[column.name] ?? null),
    format: info ? valueFormat(info) : { kind: 'number', digits: 2 },
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

/** New or dropped since the previous run (the server decides), with what it was before. */
export function changeColumn(): DataTableColumn<TableRow> {
  const was = (row: TableRow) =>
    row.change === 'dropped' && row.previousDecision
      ? ` (was ${decisionLabel(row.previousDecision).toLowerCase()})`
      : '';
  return {
    id: 'change',
    header: 'Change',
    description: 'New or dropped since the previous run',
    value: (row) => (row.change ? `${decisionLabel(row.change)}${was(row)}` : null),
    tone: 'secondary',
    width: 'sm',
  };
}
