/**
 * The review table's columns, layered: rank, ticker over name, decision (with what changed
 * since the previous run), score; one column per criterion of the screen (its value in the
 * catalogue's unit, tinted when a near miss or a miss; the gates that say who is screened get
 * none); the screen's display columns; the catalogue features the user added; the flags and
 * the reasons. A column's id is the API's sort key for it.
 */
import { Mono, Stack, Text, type DataTableColumn, type DataTableFill } from '@algotrade/ui';

import {
  displayValue,
  featureFormat,
  featureLabel,
  type CatalogueFeature,
} from '@/entities/feature';
import {
  ScreenDecisionBadge,
  type CriterionHeader,
  type ScreenTable,
  type ScreenTableRow,
} from '@/entities/screen';

const FILL: Readonly<Record<string, DataTableFill>> = {
  NEAR: 'warning',
  FAIL: 'negative',
  MISSING: 'negative',
};

const humanise = (name: string): string => {
  const words = name.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/** Who is screened is a gate, not a measurement: those criteria get no column. */
const isGate = (criterion: CriterionHeader): boolean => criterion.field.startsWith('instrument.');

function describe(feature: CatalogueFeature | undefined, field: string): string {
  return feature?.description ?? field;
}

function changeNote(row: ScreenTableRow): string | null {
  if (row.change === 'new') return 'new';
  if (row.change === 'dropped') return `dropped (was ${row.previous_decision ?? 'n/a'})`;
  return null;
}

export function resultColumns(
  table: ScreenTable,
  catalogue: ReadonlyMap<string, CatalogueFeature>,
): DataTableColumn<ScreenTableRow>[] {
  const criteria = table.criteria
    .filter((c) => !isGate(c))
    .map((c): DataTableColumn<ScreenTableRow> => {
      const feature = catalogue.get(c.field);
      return {
        id: `criterion:${c.criterion_id}`,
        header: feature ? featureLabel(feature.name) : humanise(c.criterion_id),
        description: `${describe(feature, c.field)} (criterion ${c.criterion_id}, ${c.mode}). A tint marks a near miss or a miss.`,
        value: (row) => displayValue(row.criteria[c.criterion_id]?.value),
        format: featureFormat(feature),
        fill: (row) => FILL[row.criteria[c.criterion_id]?.outcome ?? ''],
      };
    });
  const display = table.column_names.map((name): DataTableColumn<ScreenTableRow> => ({
    id: `column:${name}`,
    header: humanise(name),
    description: `The screen's column ${name}`,
    value: (row) => displayValue(row.columns[name]),
    format: { kind: 'number', digits: 2 },
  }));
  const added = table.feature_columns.map((name): DataTableColumn<ScreenTableRow> => {
    const feature = catalogue.get(name);
    return {
      id: name,
      header: featureLabel(name),
      description: `${describe(feature, name)} [${name}]`,
      value: (row) => displayValue(row.features[name]),
      format: featureFormat(feature),
    };
  });
  return [
    {
      id: 'rank',
      header: '#',
      description: 'Rank by score, then the tie-break column',
      value: (row) => row.rank,
      format: { kind: 'number' },
      width: 'xs',
      hideable: false,
    },
    {
      id: 'symbol',
      header: 'Ticker',
      description: 'The ticker and the company or fund name',
      value: (row) => row.symbol ?? row.instrument_id,
      hideable: false,
      width: 'lg',
      cell: ({ row }) => (
        <Stack gap={0}>
          <Mono weight="medium">{row.symbol ?? row.instrument_id}</Mono>
          <Text size="xs" tone="muted" truncate>
            {row.name ?? ''}
          </Text>
        </Stack>
      ),
    },
    {
      id: 'decision',
      header: 'Decision',
      description: 'The decision, and whether it is new or dropped since the previous run',
      value: (row) => row.decision,
      width: 'lg',
      cell: ({ row }) => (
        <Stack gap={0}>
          <ScreenDecisionBadge decision={row.decision} />
          {changeNote(row) ? (
            <Text size="xs" tone="muted">
              {changeNote(row)}
            </Text>
          ) : null}
        </Stack>
      ),
    },
    {
      id: 'score',
      header: 'Score',
      description: 'For sorting only: 100 minus the penalties of each miss',
      value: (row) => row.score,
      format: { kind: 'number', digits: 0 },
      width: 'xs',
    },
    ...criteria,
    ...display,
    ...added,
    {
      id: 'flags',
      header: 'Flags',
      value: (row) => row.flags.join(', ') || null,
      tone: 'secondary',
      sortable: false,
    },
    {
      id: 'reasons',
      header: 'Why',
      description: 'The misses behind a decision other than QUALIFIED',
      value: (row) => row.reasons || null,
      grow: true,
      tone: 'secondary',
      sortable: false,
    },
  ];
}
