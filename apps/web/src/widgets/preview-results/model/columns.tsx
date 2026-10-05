/**
 * The preview table's columns: rank, symbol, decision, score, one column per criterion (its
 * value in the catalogue's unit, tinted when the criterion was a near miss or a miss), the
 * screen's display columns (`[columns]`, labelled and formatted from the catalogue when the
 * name is a catalogue column), the flags and the reasons for the decision.
 */
import { type DataTableColumn, type DataTableFill } from '@algotrade/ui';

import {
  featureColumn,
  featureFormat,
  featureLabel,
  type CatalogueFeature,
} from '@/entities/feature';
import { ScreenDecisionBadge, type PreviewRow } from '@/entities/screen';

type CriterionValue = PreviewRow['criteria'][number];

const FILL: Readonly<Record<string, DataTableFill>> = {
  NEAR: 'warning',
  FAIL: 'negative',
  MISSING: 'negative',
};

/** Who is screened is a gate, not a measurement: those criteria get no column. */
const isGate = (criterion: CriterionValue): boolean => criterion.field.startsWith('instrument.');

/** The criteria the rows judged, in screen order (the first row that has them). */
export function criterionColumns(rows: readonly PreviewRow[]): CriterionValue[] {
  const first = rows.find((row) => row.criteria.length > 0);
  return (first?.criteria ?? []).filter((c) => !isGate(c));
}

const cell = (value: unknown): unknown =>
  typeof value === 'boolean' ? (value ? 'Yes' : 'No') : value;

const humanise = (name: string): string => {
  const words = name.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/** Catalogue features by the column part of their name: `pct_from_high_52w` -> its feature. */
function byColumn(catalogue: ReadonlyMap<string, CatalogueFeature>) {
  const found = new Map<string, CatalogueFeature>();
  for (const feature of catalogue.values()) {
    const column = featureColumn(feature.name);
    if (!found.has(column)) found.set(column, feature);
  }
  return found;
}

export function previewColumns(
  criteria: readonly CriterionValue[],
  extra: readonly string[],
  catalogue: ReadonlyMap<string, CatalogueFeature>,
): DataTableColumn<PreviewRow>[] {
  const criterionColumn = criteria.map((c): DataTableColumn<PreviewRow> => {
    const feature = catalogue.get(c.field);
    const of = (row: PreviewRow) => row.criteria.find((x) => x.criterion_id === c.criterion_id);
    return {
      id: `criterion:${c.criterion_id}`,
      header: feature ? featureLabel(feature.name) : humanise(c.criterion_id),
      description: `${feature?.description ?? c.field} (criterion ${c.criterion_id}, ${c.mode}). A tint marks a near miss or a miss.`,
      value: (row) => cell(of(row)?.value),
      format: featureFormat(feature),
      fill: (row) => FILL[of(row)?.outcome ?? ''],
    };
  });
  const known = byColumn(catalogue);
  const shown = new Set(criterionColumn.map((c) => c.header));
  const displayColumn = extra.flatMap((name): DataTableColumn<PreviewRow>[] => {
    const feature = known.get(name);
    const header = feature ? featureLabel(feature.name) : humanise(name);
    if (shown.has(header)) return [];
    return [
      {
        id: `col:${name}`,
        header,
        description: feature?.description ?? `The screen's column ${name}`,
        value: (row) => cell(row.columns[name]),
        format: feature ? featureFormat(feature) : { kind: 'number', digits: 2 },
      },
    ];
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
      header: 'Symbol',
      value: (row) => row.symbol ?? row.instrument_id,
      mono: true,
      hideable: false,
    },
    {
      id: 'decision',
      header: 'Decision',
      value: (row) => row.decision,
      cell: ({ row }) => <ScreenDecisionBadge decision={row.decision} />,
    },
    {
      id: 'score',
      header: 'Score',
      description: 'For sorting only: 100 minus the penalties of each miss',
      value: (row) => row.score,
      format: { kind: 'number', digits: 0 },
    },
    ...criterionColumn,
    ...displayColumn,
    {
      id: 'flags',
      header: 'Flags',
      value: (row) => row.flags.join(', ') || null,
      tone: 'secondary',
    },
    {
      id: 'reasons',
      header: 'Why',
      description: 'The misses behind a decision other than QUALIFIED',
      value: (row) => row.reasons.join('; ') || null,
      grow: true,
      tone: 'secondary',
    },
  ];
}
