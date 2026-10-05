/**
 * The holdings table's columns: rank, the holding (name over its ticker; a ticker in the
 * universe is accent-coloured and its row opens it in Explore), its weight and its type.
 */
import { Mono, Stack, Text, type DataTableColumn } from '@algotrade/ui';

import type { HoldingRow } from '@/entities/holdings';

export function holdingColumns(
  onSelectSymbol: ((symbol: string) => void) | undefined,
): DataTableColumn<HoldingRow>[] {
  return [
    {
      id: 'rank',
      header: '#',
      description: 'Position by weight in the fund',
      value: (row) => row.rank,
      format: { kind: 'number' },
      width: 'xs',
      hideable: false,
      tone: 'muted',
    },
    {
      id: 'holding',
      header: 'Holding',
      description:
        'The holding and its ticker; a coloured ticker is in the universe: its row opens it',
      value: (row) => row.name,
      width: 'lg',
      grow: true,
      hideable: false,
      cell: ({ row }) => (
        <Stack gap={0}>
          <Text size="sm" truncate title={row.name}>
            {row.name}
          </Text>
          {row.ticker !== null && (
            <Mono size="xs" tone={row.symbol !== null && onSelectSymbol ? 'accent' : 'muted'}>
              {row.ticker}
            </Mono>
          )}
        </Stack>
      ),
    },
    {
      id: 'weight',
      header: 'Weight',
      description: 'Share of the fund',
      value: (row) => row.weight,
      format: { kind: 'percent', digits: 2 },
      width: 'sm',
      hideable: false,
    },
    {
      id: 'type',
      header: 'Type',
      description: 'Asset class as the issuer reports it',
      value: (row) => row.assetClass,
      width: 'md',
      tone: 'secondary',
    },
  ];
}
