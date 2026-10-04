/**
 * The ticker table's columns: the ticker (symbol over its name), then one column per chosen
 * catalogue feature, headed by a short label and described by the catalogue (unit, meaning,
 * personal features marked), formatted by the feature's unit.
 */
import { Mono, Stack, Text, type DataTableColumn } from '@algotrade/ui';

import type { TickerRow } from '@/entities/explore';
import {
  displayValue,
  featureFormat,
  featureLabel,
  featureMarks,
  isPersonal,
  unitLabel,
  type CatalogueFeature,
} from '@/entities/feature';

const tickerColumn: DataTableColumn<TickerRow> = {
  id: 'symbol',
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

function describe(name: string, feature: CatalogueFeature | undefined): string {
  if (!feature) return name;
  const unit = unitLabel(feature.unit);
  const marks = featureMarks(feature);
  const marked = marks.length > 0 ? ` (${marks.join(', ')})` : '';
  return `${feature.description}${unit ? ` Unit: ${unit}.` : ''}${marked} [${name}]`;
}

export function tickerColumns(
  columns: readonly string[],
  catalogue: ReadonlyMap<string, CatalogueFeature>,
): DataTableColumn<TickerRow>[] {
  return [
    tickerColumn,
    ...columns.map((name): DataTableColumn<TickerRow> => {
      const feature = catalogue.get(name);
      return {
        id: name,
        header: feature && isPersonal(feature) ? `${featureLabel(name)} (P)` : featureLabel(name),
        description: describe(name, feature),
        value: (row) => displayValue(row.values[name]),
        format: featureFormat(feature),
        hideable: false,
      };
    }),
  ];
}
