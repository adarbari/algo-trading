/**
 * The compare set side by side: one row per dimension (a catalogue feature), one column per
 * ticker, each value formatted by the feature's unit; "+ Dimension" adds features.
 */
import {
  DataTable,
  formatValue,
  Mono,
  Panel,
  Stack,
  Text,
  type DataTableColumn,
} from '@algotrade/ui';
import { useMemo } from 'react';

import { FeaturePicker } from '@/features/column-picker';
import { rowValues, useCompareFeatures } from '@/entities/explore';
import {
  byName,
  displayValue,
  featureFormat,
  featureTitle,
  useFeatureCatalogue,
} from '@/entities/feature';

interface DimensionRow {
  name: string;
  values: Readonly<Record<string, unknown>>;
}

export interface SideBySideProps {
  symbols: readonly string[];
  dimensions: readonly string[];
  onDimensionsChange: (dimensions: string[]) => void;
}

export function SideBySide({ symbols, dimensions, onDimensionsChange }: SideBySideProps) {
  const compared = useCompareFeatures(symbols, dimensions);
  const catalogue = useFeatureCatalogue();
  const known = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const rows = useMemo(
    () =>
      dimensions.map((name) => ({
        name,
        values: compared.data ? rowValues(compared.data, name) : {},
      })),
    [dimensions, compared.data],
  );
  const columns = useMemo((): DataTableColumn<DimensionRow>[] => {
    const valueColumn = (symbol: string): DataTableColumn<DimensionRow> => ({
      id: symbol,
      header: symbol,
      value: (row) => row.values[symbol],
      align: 'end',
      sortable: false,
      hideable: false,
      cell: ({ row }) => {
        const shown = formatValue(
          displayValue(row.values[symbol]),
          featureFormat(known.get(row.name)),
        );
        return (
          <Text numeric tone={shown.tone}>
            {shown.text}
          </Text>
        );
      },
    });
    return [
      {
        id: 'dimension',
        header: 'Dimension',
        value: (row) => featureTitle(row.name),
        sortable: false,
        hideable: false,
        grow: true,
        width: 'lg',
        cell: ({ row }) => (
          <Stack gap={0}>
            <Text>{featureTitle(row.name)}</Text>
            <Mono size="xs" tone="muted" truncate title={row.name}>
              {row.name}
            </Mono>
          </Stack>
        ),
      },
      ...symbols.map(valueColumn),
    ];
  }, [symbols, known]);

  const state = compared.isError ? 'error' : dimensions.length === 0 ? 'empty' : 'ready';
  return (
    <Panel
      title="Side by side"
      flush
      actions={
        <FeaturePicker
          label="Dimension"
          icon="plus"
          chosen={dimensions}
          onChange={onDimensionsChange}
        />
      }
      state={state}
      emptyMessage="No dimensions: add features with + Dimension."
      errorMessage="The comparison failed to load."
      onRetry={() => void compared.refetch()}
    >
      <DataTable<DimensionRow>
        label="Side by side"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.name}
        rowLines={2}
        visibleRows={Math.max(1, rows.length)}
        status={compared.isPending ? 'loading' : 'ready'}
      />
    </Panel>
  );
}
