/**
 * Every catalogue feature for one ticker: its value for the session, unit, kind, definition
 * and (numbers only) its recent history, as the rows and columns of the features table.
 */
import {
  formatValue,
  Mono,
  Sparkline,
  Stack,
  StatusBadge,
  Text,
  type DataTableColumn,
} from '@algotrade/ui';

import {
  displayValue,
  featureFormat,
  featureTitle,
  isNumericFeature,
  featureMarks,
  unitLabel,
  type CatalogueFeature,
} from '@/entities/feature';
import {
  fieldValue,
  historyOf,
  type FeatureSeries,
  type InstrumentDetail,
} from '@/entities/instrument';

export interface FeatureRow {
  feature: CatalogueFeature;
  title: string;
  value: unknown;
  /** Values per session, oldest first; null: not a number (no sparkline). */
  history: (number | null)[] | null;
}

export function featureRows(
  catalogue: readonly CatalogueFeature[],
  detail: InstrumentDetail | undefined,
  series: FeatureSeries | undefined,
): FeatureRow[] {
  // Computed features first; the reference facts (instrument.*) after them.
  const ordered = [...catalogue].sort(
    (a, b) => Number(a.name.startsWith('instrument.')) - Number(b.name.startsWith('instrument.')),
  );
  return ordered.map((feature) => ({
    feature,
    title: featureTitle(feature.name),
    value: detail ? fieldValue(detail, feature.name) : undefined,
    history: series && isNumericFeature(feature) ? historyOf(series, feature.name) : null,
  }));
}

/** Rows whose name, title or definition contains the query. */
export function filterRows(rows: readonly FeatureRow[], query: string): readonly FeatureRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) =>
    [r.feature.name, r.title, r.feature.description].some((t) => t.toLowerCase().includes(q)),
  );
}

export function featureColumns(symbol: string): DataTableColumn<FeatureRow>[] {
  return [
    {
      id: 'feature',
      header: 'Feature',
      value: (r) => r.feature.name,
      width: 'lg',
      cell: ({ row }) => (
        <Stack gap={0}>
          <Text truncate title={row.title}>
            {[row.title, ...featureMarks(row.feature)].join(' · ')}
          </Text>
          <Mono size="xs" tone="muted" truncate title={row.feature.name}>
            {row.feature.name}
          </Mono>
        </Stack>
      ),
    },
    {
      id: 'value',
      header: 'Value',
      value: (r) => (typeof r.value === 'number' ? r.value : displayValue(r.value)),
      align: 'end',
      width: 'md',
      cell: ({ row }) => {
        const shown = formatValue(displayValue(row.value), featureFormat(row.feature));
        return (
          <Text numeric tone={shown.tone} truncate title={shown.text}>
            {shown.text}
          </Text>
        );
      },
    },
    {
      id: 'history',
      header: 'History',
      description: 'The last 90 days, one value per session',
      value: (r) => r.history?.length ?? 0,
      sortable: false,
      width: 'md',
      cell: ({ row }) =>
        row.history ? (
          <Sparkline
            values={row.history}
            label={`${symbol} ${row.title}, ${row.history.length} sessions`}
            format={featureFormat(row.feature)}
            showLast
          />
        ) : (
          <Text tone="muted">—</Text>
        ),
    },
    {
      id: 'unit',
      header: 'Unit',
      value: (r) => unitLabel(r.feature.unit),
      width: 'sm',
      tone: 'secondary',
    },
    {
      id: 'kind',
      header: 'Kind',
      value: (r) => r.feature.kind,
      width: 'sm',
      cell: ({ row }) => <StatusBadge tone="neutral">{row.feature.kind}</StatusBadge>,
    },
    {
      id: 'description',
      header: 'Definition',
      value: (r) => r.feature.description,
      grow: true,
      width: 'xl',
      tone: 'secondary',
      cell: ({ row }) => (
        <Text size="sm" tone="secondary" truncate title={row.feature.description}>
          {row.feature.description}
        </Text>
      ),
    },
  ];
}
