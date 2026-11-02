/**
 * The columns of one setup's picks (rank, ticker, its place in the setup, the other setups that
 * picked it): one pick per row, the server's order and figures, so these are typed structure and
 * not instruments x catalogue features (the exception list of `lint-rules/columns.js`).
 */
import { Mono, Stack, Text, type DataTableColumn } from '@algotrade/ui';

import type { SetupIdea } from '@/entities/idea';

export const pickColumns = (names: ReadonlyMap<string, string>): DataTableColumn<SetupIdea>[] => [
  { id: 'rank', header: 'Rank', value: (i) => i.rank, format: { kind: 'number', digits: 0 } },
  {
    id: 'ticker',
    header: 'Ticker',
    value: (i) => i.symbol ?? i.instrumentId,
    cell: ({ row }) => (
      <Stack gap={0}>
        <Mono>{row.symbol ?? row.instrumentId}</Mono>
        {row.name && (
          <Text size="sm" tone="muted">
            {row.name}
          </Text>
        )}
      </Stack>
    ),
  },
  { id: 'place', header: 'Place', value: (i) => i.place, format: { kind: 'number', digits: 0 } },
  {
    id: 'also',
    header: 'Also in',
    value: (i) => i.alsoIn.map((a) => names.get(a.edgeId) ?? a.edgeName).join(', ') || null,
  },
];
