/**
 * The episodes table's columns: the episode's name (over what kind it was), when the S&P 500 peaked
 * and bottomed, how far it fell, when it regained its peak (or that it has not), and whether the
 * NBER dated a recession in it. The rows are reference market falls, not instruments.
 */
import { Stack, Text, type DataTableColumn } from '@algotrade/ui';

import type { RegimeEpisode } from '@/entities/regime';

export const NOT_RECOVERED = 'Not yet';

export function episodeColumns(): DataTableColumn<RegimeEpisode>[] {
  return [
    {
      id: 'name',
      header: 'Episode',
      description: 'The reference market fall and what kind it was',
      value: (row) => row.name,
      width: 'xl',
      grow: true,
      hideable: false,
      cell: ({ row }) => (
        <Stack gap={0}>
          <Text size="sm">{row.name}</Text>
          <Text size="xs" tone="muted">
            {row.kind === 'recession' ? 'Recession bear market' : 'Shock or re-rating'}
          </Text>
        </Stack>
      ),
    },
    {
      id: 'peak',
      header: 'Peak',
      description: 'The S&P 500 closing high the fall started from',
      value: (row) => row.peak,
      format: { kind: 'date' },
      hideable: false,
    },
    {
      id: 'trough',
      header: 'Trough',
      description: 'The S&P 500 closing low',
      value: (row) => row.trough,
      format: { kind: 'date' },
    },
    {
      id: 'fall',
      header: 'S&P 500 fall',
      description: 'Peak to trough, closing basis',
      value: (row) => row.spxDrawdown,
      format: { kind: 'percent', digits: 0 },
    },
    {
      id: 'recovered',
      header: 'Recovered',
      description: 'The first session the S&P 500 closed at or above its peak again',
      value: (row) => row.recovered,
      format: { kind: 'date' },
      cell: ({ row, formatted }) => (row.recovered === null ? NOT_RECOVERED : formatted.text),
    },
    {
      id: 'recession',
      header: 'NBER recession',
      description: 'The NBER dated a recession that overlapped the fall',
      value: (row) => (row.recession ? 'Yes' : 'No'),
      tone: 'secondary',
    },
  ];
}
